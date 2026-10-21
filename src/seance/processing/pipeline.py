from __future__ import annotations

import argparse
import threading
from pathlib import Path
from typing import Callable

from ..common import log
from ..layout import get_transcript_path, has_audio
from ..media.audio_import import import_audio_file
from ..sessions import resolve_session
from .minutes import summarize
from .transcription import transcribe

StatusCallback = Callable[[str], None]


def _notify(callback: StatusCallback | None, message: str) -> None:
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        # Status display is advisory and must never break the actual pipeline.
        pass


def transcribe_folder(
    folder: str | Path,
    source_args: argparse.Namespace,
    *,
    on_status: StatusCallback | None = None,
) -> None:
    """Run Whisper for one explicitly selected session, reporting major stages."""
    callback = on_status or getattr(source_args, "status_callback", None)
    selected = Path(folder).expanduser().resolve()
    _notify(callback, "Whisper · préparation des pistes audio…")
    args = argparse.Namespace(
        folder=str(selected),
        directory=getattr(source_args, "directory", "seances"),
        model=getattr(source_args, "model", "models/asr/model.bin"),
        whisper_cli=getattr(source_args, "whisper_cli", "bin/asr/whisper-cli.exe"),
        transcription_provider=getattr(source_args, "transcription_provider", "whisper.cpp"),
        provider_options=getattr(source_args, "provider_options", {}),
        language=getattr(source_args, "language", "auto"),
        threads=getattr(source_args, "threads", 1),
        ffmpeg=getattr(source_args, "ffmpeg", "ffmpeg"),
        diarize=getattr(source_args, "diarize", False),
        diarization_segmentation_model=getattr(source_args, "diarization_segmentation_model", "models/diarization/segmentation/segmentation.onnx"),
        diarization_embedding_model=getattr(source_args, "diarization_embedding_model", "models/diarization/embedding/embedding.onnx"),
        diarization_num_speakers=getattr(source_args, "diarization_num_speakers", -1),
        diarization_threshold=getattr(source_args, "diarization_threshold", 0.5),
        _cancel_event=getattr(source_args, "_cancel_event", None),
        status_callback=callback,
        artifact_event_callback=getattr(source_args, "artifact_event_callback", None),
    )
    from ..providers.events import reset_provider_event_callback, set_provider_event_callback
    event_callback = getattr(source_args, "provider_event_callback", None)
    if event_callback is None and callback is not None:
        event_callback = lambda event: _notify(callback, event.message)
    event_token = set_provider_event_callback(event_callback) if event_callback is not None else None
    try:
        transcribe(args)
    finally:
        if event_token is not None:
            reset_provider_event_callback(event_token)
    _notify(callback, "Whisper · transcription enregistrée")


def _summary_activity_snapshot(folder: Path) -> dict[str, object]:
    """Snapshot known generated artifacts so the web UI can show long-running LLM work."""
    analysis = folder / "analysis"
    summary = folder / "summary"
    parts: dict[str, tuple[int, int]] = {}
    try:
        for path in (analysis / "parts").glob("*.md"):
            try:
                stat = path.stat()
                parts[path.name] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue
    except OSError:
        pass

    artifacts: dict[str, tuple[int, int] | None] = {}
    for key, path in (
        ("format", analysis / "format_selection.txt"),
        ("analyses", analysis / "analyses.md"),
        ("notes", analysis / "notes_pour_redaction.md"),
        ("draft", summary / "resume_audio_initial.md"),
        ("final", summary / "resume_audio.md"),
    ):
        try:
            stat = path.stat()
            artifacts[key] = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            artifacts[key] = None
    return {"parts": parts, "artifacts": artifacts}


def _watch_summary_activity(
    folder: Path,
    callback: StatusCallback,
    stop: threading.Event,
    initial: dict[str, object],
) -> None:
    """Publish coarse but truthful progress as summary artifacts are created/updated."""
    previous = initial
    stage_rank = 0
    while not stop.wait(0.8):
        current = _summary_activity_snapshot(folder)
        previous_parts = previous.get("parts", {})
        current_parts = current.get("parts", {})
        changed_parts = [
            name for name, signature in current_parts.items()
            if previous_parts.get(name) != signature
        ]
        old_artifacts = previous.get("artifacts", {})
        new_artifacts = current.get("artifacts", {})
        candidates = [
            rank for key, rank in (("format", 2), ("analyses", 2), ("notes", 3), ("draft", 4), ("final", 5))
            if new_artifacts.get(key) is not None and new_artifacts.get(key) != old_artifacts.get(key)
        ]
        candidate_rank = max(candidates, default=0)
        if changed_parts:
            candidate_rank = max(candidate_rank, 1)
        stage_rank = max(stage_rank, candidate_rank)
        stage_text = {
            0: "LLM · analyse des thèmes et préparation de la rédaction…",
            1: f"LLM · analyse des contenus en cours ({len(current_parts)} partie(s) d'analyse visibles)…",
            2: "LLM · consolidation des analyses et sélection du format…",
            3: "LLM · notes de rédaction actualisées, préparation du résumé…",
            4: "LLM · brouillon rédigé, relecture et finalisation en cours…",
            5: "LLM · fichier de résumé final actualisé…",
        }.get(stage_rank, "LLM · traitement en cours…")
        if candidate_rank or changed_parts:
            _notify(callback, stage_text)
        previous = current


def minutes_folder(
    folder: str | Path,
    source_args: argparse.Namespace,
    *,
    on_status: StatusCallback | None = None,
) -> None:
    """Generate an adaptive report and monitor its intermediate artifacts for the Web UI."""
    callback = on_status or getattr(source_args, "status_callback", None)
    selected = Path(folder).expanduser().resolve()
    _notify(callback, "LLM · analyse des thèmes et préparation de la rédaction…")
    args = argparse.Namespace(
        folder=str(selected),
        directory=getattr(source_args, "directory", "seances"),
        gguf=getattr(source_args, "gguf", "models/llm/model.gguf"),
        llama_completion=getattr(source_args, "llama_completion", "bin/llm/llama-completion.exe"),
        text_provider=getattr(source_args, "text_provider", "llama.cpp"),
        provider_options=getattr(source_args, "provider_options", {}),
        context=getattr(source_args, "context", 16384),
        max_tokens=getattr(source_args, "max_tokens", 6000),
        analysis_tokens=getattr(source_args, "analysis_tokens", 3500),
        analysis_retries=getattr(source_args, "analysis_retries", 3),
        analysis_max_splits=getattr(source_args, "analysis_max_splits", 6),
        format=getattr(source_args, "format", "auto"),
        no_review=getattr(source_args, "no_review", False),
        diarize=getattr(source_args, "diarize", False),
        diarization_segmentation_model=getattr(source_args, "diarization_segmentation_model", "models/diarization/segmentation/segmentation.onnx"),
        diarization_embedding_model=getattr(source_args, "diarization_embedding_model", "models/diarization/embedding/embedding.onnx"),
        diarization_num_speakers=getattr(source_args, "diarization_num_speakers", -1),
        diarization_threshold=getattr(source_args, "diarization_threshold", 0.5),
        _cancel_event=getattr(source_args, "_cancel_event", None),
        status_callback=callback,
        artifact_event_callback=getattr(source_args, "artifact_event_callback", None),
    )
    monitor_stop = threading.Event()
    monitor: threading.Thread | None = None
    if callback is not None:
        monitor = threading.Thread(
            target=_watch_summary_activity,
            args=(selected, callback, monitor_stop, _summary_activity_snapshot(selected)),
            name=f"seance-summary-watch-{selected.name}",
            daemon=True,
        )
        monitor.start()
    try:
        from ..llm import reset_job_cancel_event, set_job_cancel_event
        from ..providers.events import reset_provider_event_callback, set_provider_event_callback
        from ..providers.selection import reset_text_provider, set_text_provider
        cancel_token = set_job_cancel_event(getattr(args, "_cancel_event", None))
        provider_options = getattr(args, "provider_options", {}) or {}
        provider_id = getattr(args, "text_provider", None)
        provider_token = set_text_provider(provider_id, provider_options.get(provider_id or "", {}))
        event_callback = getattr(source_args, "provider_event_callback", None)
        if event_callback is None and callback is not None:
            event_callback = lambda event: _notify(callback, event.message)
        event_token = set_provider_event_callback(event_callback) if event_callback is not None else None
        summarize(args)
    finally:
        if "event_token" in locals() and event_token is not None:
            reset_provider_event_callback(event_token)
        if "provider_token" in locals():
            reset_text_provider(provider_token)
        if "cancel_token" in locals():
            reset_job_cancel_event(cancel_token)
        monitor_stop.set()
        if monitor is not None:
            monitor.join(timeout=1.5)
    _notify(callback, "LLM · résumé final enregistré")


def process_folder(
    folder: str | Path,
    source_args: argparse.Namespace,
    *,
    on_status: StatusCallback | None = None,
) -> None:
    """Transcribe if needed, then create a report, publishing stage updates."""
    callback = on_status or getattr(source_args, "status_callback", None)
    selected = Path(folder).expanduser().resolve()
    if not selected.is_dir():
        raise SystemExit(f"Session directory not found: {selected}")

    transcript = get_transcript_path(selected)
    if not transcript.is_file():
        if not has_audio(selected):
            raise SystemExit(
                f"Neither transcript/transcription.md nor a supported audio track was found in {selected}."
            )
        _notify(callback, "Transcription absente · lancement de Whisper…")
        log("Transcript not found; starting Whisper transcription.")
        transcribe_folder(selected, source_args, on_status=callback)
    else:
        _notify(callback, "Transcription existante détectée · réutilisation du texte")
        log("Existing transcript found; skipping Whisper.")

    _notify(callback, "Transcription prête · génération du résumé local…")
    minutes_folder(selected, source_args, on_status=callback)
    _notify(callback, "Résumé terminé · séance prête à consulter")


def process(args: argparse.Namespace) -> None:
    """Process an explicit session or latest suitable session in the session root."""
    requested = getattr(args, "folder", None)
    if requested and Path(requested).expanduser().is_file():
        folder = import_audio_file(
            requested,
            getattr(args, "directory", "seances"),
            ffmpeg=getattr(args, "ffmpeg", "ffmpeg"),
        )
    else:
        folder = resolve_session(
            requested,
            getattr(args, "directory", "seances"),
            require="processable",
        )
    process_folder(folder, args)
