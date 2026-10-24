"""Optional, local speech enhancement before ASR.

The original recording is never overwritten. Enhancement runs on temporary chunks
created by the transcription use case, keeping long sessions bounded in memory.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


VALID_MODES = {"auto", "off", "ffmpeg", "deepfilter"}


def _available(executable: str | Path | None) -> bool:
    if not executable:
        return False
    value = str(executable).strip()
    if not value:
        return False
    if "/" in value or "\\" in value:
        return Path(value).expanduser().is_file()
    return shutil.which(value) is not None


def _run_cancellable(
    command: list[str], *, cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess[str]:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Prétraitement audio annulé.")
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    while True:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise RuntimeError("Prétraitement audio annulé.")
        try:
            stdout, stderr = process.communicate(timeout=0.25)
            return subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


def _check_output(path: Path, result: subprocess.CompletedProcess[str], description: str) -> None:
    if result.returncode != 0 or not path.is_file() or path.stat().st_size <= 44:
        detail = (result.stderr or result.stdout or "aucun détail fourni").strip()
        raise RuntimeError(f"{description} a échoué : {detail[-3000:]}")


def enhance_for_transcription(
    source: str | Path,
    target: str | Path,
    *,
    mode: str = "auto",
    ffmpeg: str = "ffmpeg",
    deep_filter_executable: str | Path = "bin/speech/deep-filter.exe",
    deep_filter_model: str | Path = "models/speech-enhancement/model.tar.gz",
    cancel_event: threading.Event | None = None,
) -> tuple[Path, str]:
    """Create a speech-enhanced 16 kHz mono WAV and return (path, selected_mode).

    ``ffmpeg`` uses conservative high/low-pass filtering and spectral denoising. The
    optional DeepFilterNet backend is a learned speech-enhancement model and requires
    a separately installed binary and model archive. Neither mode separates two
    simultaneously speaking people into individual stems.
    """
    source_path = Path(source).expanduser().resolve()
    target_path = Path(target).expanduser().resolve()
    requested_mode = str(mode or "auto").strip().lower()
    if requested_mode not in VALID_MODES:
        raise ValueError(f"Mode de prétraitement inconnu : {requested_mode}")
    if requested_mode == "off":
        return source_path, "off"

    deep_exe = str(deep_filter_executable or "").strip()
    deep_model = Path(deep_filter_model).expanduser() if deep_filter_model else Path()
    deep_ready = _available(deep_exe) and bool(str(deep_filter_model or "").strip()) and deep_model.is_file()
    selected = requested_mode
    if requested_mode == "auto":
        selected = "deepfilter" if deep_ready else ("ffmpeg" if _available(ffmpeg) else "off")
    if selected == "off":
        return source_path, "off"
    if selected == "deepfilter" and not deep_ready:
        raise RuntimeError(
            "Le prétraitement DeepFilterNet est activé mais le binaire ou le modèle manque. "
            "Installez deep-filter et placez l'archive du modèle à "
            "models/speech-enhancement/model.tar.gz, ou choisissez le mode auto/FFmpeg."
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if selected == "ffmpeg":
        # Moderate filtering is deliberately chosen to avoid erasing quiet consonants.
        command = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_path),
            "-vn", "-af", "highpass=f=65,lowpass=f=7600,afftdn=nr=8:nf=-45:tn=1",
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target_path),
        ]
        try:
            result = _run_cancellable(command, cancel_event=cancel_event)
            _check_output(target_path, result, "Le débruitage FFmpeg")
        except (OSError, RuntimeError) as exc:
            if requested_mode == "auto" and not (cancel_event is not None and cancel_event.is_set()):
                # Auto mode should never make an otherwise valid recording unusable.
                # If this FFmpeg build lacks afftdn or filtering fails, use the source.
                return source_path, "off"
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Impossible de lancer FFmpeg pour améliorer la voix : {exc}") from exc
        return target_path, "ffmpeg"

    # The Rust DeepFilterNet CLI expects 48 kHz WAV. Work on one ASR chunk at a time,
    # not the whole four-hour source, and resample the enhanced result back to ASR's
    # standard 16 kHz mono representation.
    try:
        with tempfile.TemporaryDirectory(prefix="glimio-deepfilter-", dir=str(target_path.parent)) as tmp:
            temp_dir = Path(tmp)
            input_48k = temp_dir / "input_48k.wav"
            output_dir = temp_dir / "enhanced"
            output_dir.mkdir()
            convert_in = [
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_path),
                "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(input_48k),
            ]
            try:
                converted = _run_cancellable(convert_in, cancel_event=cancel_event)
            except OSError as exc:
                raise RuntimeError(f"Impossible de préparer l'audio pour DeepFilterNet : {exc}") from exc
            _check_output(input_48k, converted, "La conversion audio 48 kHz")
            enhance_command = [
                deep_exe, "--model", str(deep_model.resolve()), "--output-dir", str(output_dir),
                "--compensate-delay", str(input_48k),
            ]
            try:
                enhanced_result = _run_cancellable(enhance_command, cancel_event=cancel_event)
            except OSError as exc:
                raise RuntimeError(f"Impossible de lancer DeepFilterNet : {exc}") from exc
            candidates = [p for p in output_dir.glob("*.wav") if p.is_file() and p.stat().st_size > 44]
            if enhanced_result.returncode != 0 or not candidates:
                detail = (enhanced_result.stderr or enhanced_result.stdout or "aucun fichier de sortie créé").strip()
                raise RuntimeError(f"DeepFilterNet a échoué : {detail[-3000:]}")
            enhanced_input = max(candidates, key=lambda p: p.stat().st_mtime)
            convert_out = [
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(enhanced_input),
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target_path),
            ]
            try:
                converted_out = _run_cancellable(convert_out, cancel_event=cancel_event)
            except OSError as exc:
                raise RuntimeError(f"Impossible de ramener la voix améliorée à 16 kHz : {exc}") from exc
            _check_output(target_path, converted_out, "La conversion audio améliorée")
        return target_path, "deepfilter"
    except (OSError, RuntimeError) as exc:
        if requested_mode == "auto" and not (cancel_event is not None and cancel_event.is_set()):
            # A stale/incompatible external model should not block transcription. Try
            # the dependency-light filter, then keep the original if even that fails.
            try:
                return enhance_for_transcription(
                    source_path, target_path, mode="ffmpeg", ffmpeg=ffmpeg,
                    deep_filter_executable=deep_filter_executable, deep_filter_model=deep_filter_model,
                    cancel_event=cancel_event,
                )
            except (OSError, RuntimeError, ValueError):
                return source_path, "off"
        raise
