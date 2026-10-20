from __future__ import annotations

"""Shared local llama.cpp execution helpers used by Glimio services.

This module centralizes command compatibility, context budgeting, cancellation,
output decoding/cleaning, and retries. It deliberately does not own application
prompts: minutes and cross-session search provide their own instructions.
"""

import math
import re
import subprocess
import threading
import time
from contextvars import ContextVar, Token
from functools import lru_cache
from pathlib import Path
from typing import Callable

from .runtime import AI_ENGINE_LOCK, acquire_ai_engine

_JOB_CANCEL_EVENT: ContextVar[threading.Event | None] = ContextVar("glimio_job_cancel_event", default=None)


def set_job_cancel_event(event: threading.Event | None) -> Token[threading.Event | None]:
    return _JOB_CANCEL_EVENT.set(event)


def reset_job_cancel_event(token: Token[threading.Event | None]) -> None:
    _JOB_CANCEL_EVENT.reset(token)


class LLMError(RuntimeError):
    """A local model could not produce a usable response."""


class LLMCancelled(LLMError):
    """Generation was cancelled by the caller."""




def clean_model_output(text: str) -> str:
    """Return only user-facing model text; discard reasoning and template tokens.

    If a model starts a private reasoning block and stops before closing it, the
    remainder is discarded. An empty result is preferable to leaking scratch text.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Prefer an explicit final channel if a template returned multiple channels.
    final_patterns = (
        r"<\|channel\|>\s*final\b",
        r"<\|im_start\|>\s*assistant\s+final\b",
        r"<\|assistant\|>\s*<\|final\|>",
    )
    final_positions = [
        match.end()
        for pattern in final_patterns
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]
    if final_positions:
        text = text[max(final_positions):]

    # Stop on known end-of-turn markers before removing wrappers.
    end_marker = re.search(
        r"\[end of text\]|\[end of turn\]|\[fim_suffix\]|"
        r"<\|(?:fim_suffix|endoftext|im_end|eot_id|end_of_turn)\|>|</s>",
        text,
        flags=re.IGNORECASE,
    )
    if end_marker:
        text = text[:end_marker.start()]

    for tag in ("think", "analysis", "reasoning", "scratchpad"):
        text = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}\s*>",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # Unclosed private channels must not leak through to the UI or report.
        text = re.sub(
            rf"<{tag}\b[^>]*>.*\Z",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    text = re.sub(
        r"<\|(?:im_start|im_end|eot_id|end_of_turn|assistant|user|system|final|"
        r"fim_suffix|endoftext|fim_prefix|fim_middle|ghissue|ghreview|startoftext|"
        r"message_start|message_end)\|>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<\|channel\|>\s*(?:analysis|final|commentary)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^\s*(?:assistant|final|réponse(?: finale)?)\s*[:：]\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?im)^\s*(?:assistant|user|system)\s*$\n?", "", text)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text.strip()


def decode_process_output(data: bytes | str | None) -> str:
    """Decode native process output with UTF-8 first and a Windows fallback."""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def estimate_tokens(text: str) -> int:
    """Conservative token estimate used to bound prompts and outputs."""
    return max(1, math.ceil(len(text) / 3.2))


def estimated_output_room(system_prompt: str, user_prompt: str, context: int) -> int:
    prompt_chars = len(system_prompt) + len(user_prompt) + 1200
    estimated_prompt_tokens = estimate_tokens(" " * prompt_chars)
    return max(0, context - estimated_prompt_tokens - 256)


def generation_hit_limit(stderr_text: str, max_tokens: int) -> bool:
    counts = re.findall(
        r"eval time\s*=.*?/\s*(\d+)\s+runs",
        stderr_text,
        flags=re.IGNORECASE,
    )
    return bool(counts) and int(counts[-1]) >= max_tokens - 2


def stderr_without_logs(stderr_text: str) -> str:
    patterns = (
        r"common_perf_print", r"sampling time\s*=", r"samplers time\s*=",
        r"load time\s*=", r"prompt eval time\s*=", r"eval time\s*=",
        r"total time\s*=", r"unaccounted time\s*=", r"sampler chain:",
        r"graphs reused\s*=", r"graph reallocs\s*=", r"n_ctx\s*=",
        r"n_batch\s*=", r"n_predict\s*=", r"^\s*\d+\.\d+\.\d+\.\d+\s+[A-Z]\s+",
        r"^\s*(?:warning|error):",
    )
    return "\n".join(
        line for line in stderr_text.splitlines()
        if not any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)
    ).strip()


@lru_cache(maxsize=16)
def llama_help_text(binary: str, modified_ns: int) -> str:
    """Cache this executable's CLI help so arguments fit the installed llama.cpp build."""
    del modified_ns  # part of the cache key; invalidates when the binary changes.
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
        return (result.stdout or "") + "\n" + (result.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


def build_completion_command(
    executable: Path,
    model_path: Path,
    *,
    context: int,
    max_tokens: int,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
) -> tuple[list[str], int]:
    """Build one non-interactive completion, using a chat template when supported."""
    binary = Path(executable).expanduser().resolve()
    model = Path(model_path).expanduser().resolve()
    try:
        mtime_ns = binary.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    help_text = llama_help_text(str(binary), mtime_ns)
    has_single_turn_short = re.search(r"(?<!\w)-st(?:,|\s)", help_text) is not None
    has_conversation_short = re.search(r"(?<!\w)-cnv(?:,|\s)", help_text) is not None
    has_no_conversation_short = re.search(r"(?<!\w)-no-cnv(?:,|\s)", help_text) is not None
    single_turn_flag = "--single-turn" if "--single-turn" in help_text else ("-st" if has_single_turn_short else None)
    conversation_flag = "--conversation" if "--conversation" in help_text else ("-cnv" if has_conversation_short else None)
    no_conversation_flag = "--no-conversation" if "--no-conversation" in help_text else ("-no-cnv" if has_no_conversation_short else None)

    if single_turn_flag and conversation_flag:
        mode_flags = [conversation_flag, single_turn_flag]
    elif no_conversation_flag:
        mode_flags = [no_conversation_flag]
    elif single_turn_flag:
        # A predefined prompt plus single-turn mode must exit after one response.
        mode_flags = [single_turn_flag]
    elif not help_text:
        # Compatibility fallback for native builds that do not print usable --help.
        mode_flags = ["-no-cnv"]
    else:
        raise LLMError(
            "Impossible de confirmer un mode llama.cpp non interactif avec cet exécutable. "
            "Vérifie que tu utilises llama-completion.exe et que son --help expose "
            "-no-cnv/--no-conversation ou -st/--single-turn."
        )

    command = [
        str(binary), "-m", str(model), "-c", str(context), "-n", str(max_tokens),
        "--temp", str(temperature), *mode_flags,
    ]

    if "--no-display-prompt" in help_text:
        command.append("--no-display-prompt")
    if conversation_flag in mode_flags and single_turn_flag in mode_flags and re.search(
        r"(?m)^\s*(?:--jinja|.*[, ]--jinja)(?:[, ]|\s|$)", help_text
    ):
        command.append("--jinja")
    if re.search(r"(?m)^\s*(?:-[\w-]+,\s*)?--reasoning(?:\s|,|$)", help_text):
        command.extend(["--reasoning", "off"])
    if "--reasoning-budget" in help_text:
        command.extend(["--reasoning-budget", "0"])

    system_flag = "-sys" if re.search(r"(?<!\w)-sys(?:,|\s)", help_text) else (
        "--system-prompt" if "--system-prompt" in help_text else None
    )
    prompt_flag = "-p" if re.search(r"(?<!\w)-p(?:,|\s)", help_text) else (
        "--prompt" if "--prompt" in help_text else None
    )
    if not help_text:
        prompt_flag = "-p"
    if system_flag and prompt_flag:
        command.extend([system_flag, system_prompt, prompt_flag, user_prompt])
    elif prompt_flag:
        command.extend([prompt_flag, system_prompt + "\n\n" + user_prompt])
    else:
        # Do not silently fall back to positional text when --help exists but does not
        # advertise a prompt flag: on some builds that enters an interactive prompt.
        if help_text:
            raise LLMError(
                "Impossible de trouver un paramètre de prompt compatible dans l'aide de llama.cpp. "
                "Attendu : -p/--prompt, éventuellement avec -sys/--system-prompt."
            )
        command.append(system_prompt + "\n\n" + user_prompt)

    output_room = estimated_output_room(system_prompt, user_prompt, context)
    if output_room < 128:
        raise LLMError(
            f"Le prompt est trop long pour un contexte de {context} tokens. "
            "Réduis le nombre d'extraits ou augmente le contexte."
        )
    effective_tokens = min(max_tokens, output_room)
    command[command.index("-n") + 1] = str(effective_tokens)
    return command, effective_tokens


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.poll() is None:
            process.terminate()
    except OSError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def run_completion_once(
    executable: Path,
    model_path: Path,
    working_directory: Path,
    system_prompt: str,
    user_prompt: str,
    *,
    context: int,
    max_tokens: int,
    temperature: float = 0.2,
    stage: str = "Génération locale",
    cancel_event: threading.Event | None = None,
    on_process: Callable[[subprocess.Popen[bytes] | None], None] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[str, bool]:
    """Execute one completion. Supports cancellation and process publication to a UI.

    By default there is no wall-clock timeout, preserving the CLI's former behaviour on
    slow CPU-only machines. Interactive Web searches pass an explicit bounded timeout.
    """
    if cancel_event is None:
        cancel_event = _JOB_CANCEL_EVENT.get()
    if cancel_event is not None and cancel_event.is_set():
        raise LLMCancelled("Génération annulée.")
    executable = Path(executable).expanduser().resolve()
    model_path = Path(model_path).expanduser().resolve()
    if not executable.is_file():
        raise LLMError(f"Exécutable llama.cpp introuvable : {executable}")
    if not model_path.is_file():
        raise LLMError(f"Modèle GGUF introuvable : {model_path}")

    command, effective_tokens = build_completion_command(
        executable,
        model_path,
        context=context,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    # Waiting for the shared engine slot remains cancellable (especially for
    # interactive cross-session search). Audio capture intentionally bypasses the lock.
    if not acquire_ai_engine(cancel_event):
        raise LLMCancelled("Génération annulée avant le démarrage du moteur local.")

    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(Path(working_directory).resolve()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        if on_process:
            try:
                on_process(process)
            except Exception:
                # UI state publication is advisory; cancellation remains checked below.
                pass
        started = time.monotonic()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process(process)
                raise LLMCancelled("Génération annulée.")
            elapsed = time.monotonic() - started
            if timeout_seconds is not None and elapsed > timeout_seconds:
                _terminate_process(process)
                raise LLMError(
                    f"La génération '{stage}' a dépassé {int(timeout_seconds)} secondes."
                )
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
    except OSError as exc:
        raise LLMError(f"Impossible de lancer llama.cpp : {exc}") from exc
    finally:
        if on_process:
            try:
                on_process(None)
            except Exception:
                pass
        AI_ENGINE_LOCK.release()

    if cancel_event is not None and cancel_event.is_set():
        raise LLMCancelled("Génération annulée.")
    stdout_text = decode_process_output(stdout)
    stderr_text = decode_process_output(stderr)
    if process.returncode != 0:
        detail = (stderr_text or stdout_text or "Erreur sans détail").strip()[-6000:]
        raise LLMError(
            f"llama.cpp a échoué pendant '{stage}' (code {process.returncode}).\n{detail}"
        )

    output = clean_model_output(stdout_text)
    if not output:
        candidate = clean_model_output(stderr_without_logs(stderr_text))
        if candidate:
            output = candidate
    if not output:
        diagnostic = f"llama.cpp n'a renvoyé aucun texte exploitable pendant '{stage}'."
        if stdout_text.strip():
            diagnostic += "\nDébut de stdout :\n" + stdout_text[:1200]
        if stderr_text.strip():
            diagnostic += "\nFin de stderr :\n" + stderr_text[-1600:]
        raise LLMError(diagnostic)

    hit_limit = generation_hit_limit(stderr_text, effective_tokens)
    return output, hit_limit


def run_completion_resilient(
    executable: Path,
    model_path: Path,
    working_directory: Path,
    system_prompt: str,
    user_prompt: str,
    *,
    context: int,
    max_tokens: int,
    temperature: float = 0.2,
    stage: str = "Génération locale",
    retries: int = 2,
    cancel_event: threading.Event | None = None,
    on_process: Callable[[subprocess.Popen[bytes] | None], None] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[str, bool]:
    """Retry truncated outputs with a larger budget, preserving cancellation semantics."""
    output_room = estimated_output_room(system_prompt, user_prompt, context)
    if output_room < 128:
        raise LLMError(
            f"Le prompt de '{stage}' laisse trop peu de place à la génération dans "
            f"un contexte de {context} tokens. Réduis les extraits ou augmente le contexte."
        )
    current_limit = min(max_tokens, output_room)
    best_text = ""
    best_hit_limit = True
    for attempt in range(max(0, retries) + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise LLMCancelled("Génération annulée.")
        candidate, hit_limit = run_completion_once(
            executable,
            model_path,
            working_directory,
            system_prompt,
            user_prompt,
            context=context,
            max_tokens=current_limit,
            temperature=temperature,
            stage=stage if attempt == 0 else f"{stage} (nouvel essai {attempt}/{retries})",
            cancel_event=cancel_event,
            on_process=on_process,
            timeout_seconds=timeout_seconds,
        )
        if not best_text or len(candidate) > len(best_text):
            best_text, best_hit_limit = candidate, hit_limit
        if not hit_limit:
            return candidate, False
        if attempt >= retries or current_limit >= output_room:
            break
        next_limit = min(output_room, max(current_limit + 1200, math.ceil(current_limit * 1.6)))
        if next_limit <= current_limit:
            break
        current_limit = next_limit
    return best_text, best_hit_limit
