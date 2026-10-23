from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from ..common import log
from ..layout import ensure_session_layout, get_audio_path, transcript_output_path
from ..media.audio_import import import_audio_file
from ..providers import DEFAULT_TRANSCRIPTION_PROVIDER, create_transcription_provider
from ..providers.contracts import TranscriptionRequest
from ..sessions import resolve_session
from .diarization_process import diarize_transcription_isolated

TRANSCRIPTION_CHUNK_SECONDS = 15 * 60
TRANSCRIPTION_CHUNK_OVERLAP_SECONDS = 10


def _status(args: argparse.Namespace, message: str) -> None:
    callback = getattr(args, "status_callback", None)
    if callable(callback):
        try:
            callback(message)
        except Exception:
            # Progress reporting is optional and must not affect transcription.
            pass


def _publish_artifact_update(args: argparse.Namespace, kind: str) -> None:
    callback = getattr(args, "artifact_event_callback", None)
    if callable(callback):
        try:
            callback(kind)
        except Exception:
            # Live previews are optional and must not interrupt transcription.
            pass


def _stamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _srt_stamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def _audio_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as source:
            rate = source.getframerate()
            return source.getnframes() / rate if rate > 0 else None
    except (OSError, wave.Error, EOFError):
        return None


def _extract_chunk(source: Path, target: Path, start: float, end: float, ffmpeg: str,
                   cancel_event: Any = None) -> None:
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}",
        "-i", str(source), "-t", f"{max(0.1, end - start):.3f}", "-c", "copy", str(target),
    ]
    try:
        result = _run_cancellable_command(command, cwd=source.parent, cancel_event=cancel_event)
    except OSError as exc:
        raise SystemExit(f"Could not extract an audio chunk with {ffmpeg}: {exc}") from exc
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        detail = result.stderr.strip()[-2000:]
        raise SystemExit(f"Could not extract audio chunk from {source.name}: {detail or result.returncode}")


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text.rstrip() + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SystemExit(f"Could not write {path}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _render_transcript(segments: list[dict[str, Any]], *, in_progress: bool = False) -> str:
    lines = [
        "# Transcription audio", "",
        "Les étiquettes indiquent la piste source (Micro, Audio Windows ou Audio importé), pas nécessairement l'identité des personnes. Cette version ne réalise pas de diarisation automatique.", "",
    ]
    if in_progress:
        lines.extend(["> Transcription partielle, actualisée après chaque segment audio traité.", ""])
    for item in segments:
        lines.append(
            f"[{_stamp(item['start'])}–{_stamp(item['end'])}] "
            f"**{item['speaker']}**: {item['text']}"
        )
    return "\n".join(lines) + "\n"


def _run_cancellable_command(command: list[str], *, cwd: Path, cancel_event: Any = None) -> subprocess.CompletedProcess[str]:
    if cancel_event is not None and cancel_event.is_set():
        raise SystemExit("Traitement annulé.")
    process = subprocess.Popen(
        command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    while True:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise SystemExit("Traitement annulé.")
        try:
            stdout, stderr = process.communicate(timeout=0.25)
            return subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


def transcribe(args: argparse.Namespace) -> None:
    executable = Path(args.whisper_cli).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()

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
            require="audio",
        )

    ensure_session_layout(folder)
    all_segments: list[dict[str, Any]] = []
    tracks_found = 0
    transcript_dir = folder / "transcript"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    from ..layout import list_audio_paths
    metadata_sources: dict[str, dict[str, Any]] = {}
    disabled_tracks: set[str] = set()
    metadata_value: dict[str, Any] = {}
    try:
        import json
        metadata_path = folder / "metadata" / "seance.json"
        if not metadata_path.is_file():
            metadata_path = folder / "seance.json"
        metadata_value = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.is_file() else {}
        raw_disabled = metadata_value.get("disabled_audio_tracks", []) if isinstance(metadata_value, dict) else []
        if isinstance(raw_disabled, list):
            disabled_tracks = {name for name in raw_disabled if isinstance(name, str)}
        raw_sources = metadata_value.get("audio_sources", []) if isinstance(metadata_value, dict) else []
        if isinstance(raw_sources, list):
            metadata_sources = {str(item.get("filename")): item for item in raw_sources if isinstance(item, dict) and item.get("filename")}
    except (OSError, ValueError, TypeError):
        metadata_sources = {}
    tracks = [path for path in list_audio_paths(folder) if path.name not in disabled_tracks]
    (transcript_dir / "transcription_en_cours.md").unlink(missing_ok=True)
    provider = create_transcription_provider(
        getattr(args, "transcription_provider", DEFAULT_TRANSCRIPTION_PROVIDER),
        executable,
        cancel_event=getattr(args, "_cancel_event", None),
        options=(getattr(args, "provider_options", {}) or {}).get(
            getattr(args, "transcription_provider", DEFAULT_TRANSCRIPTION_PROVIDER), {},
        ),
    )
    for audio_path in tracks:
        cancel_event = getattr(args, "_cancel_event", None)
        if cancel_event is not None and cancel_event.is_set():
            raise SystemExit("Traitement annulé.")
        filename = audio_path.name
        source_meta = metadata_sources.get(filename, {})
        if source_meta.get("name"):
            source_name = str(source_meta["name"])
        elif filename == "micro.wav":
            source_name = "Micro"
        elif filename == "windows.wav":
            source_name = "Audio Windows"
        elif filename == "audio_import.wav":
            source_name = "Audio importé"
        else:
            source_name = filename[:-4].replace("-", " ").replace("_", " ").title()
        tracks_found += 1
        duration = _audio_duration(audio_path)
        if duration is not None and duration > TRANSCRIPTION_CHUNK_SECONDS:
            chunk_ranges = []
            chunk_count = (int(duration) + TRANSCRIPTION_CHUNK_SECONDS - 1) // TRANSCRIPTION_CHUNK_SECONDS
            for chunk_index in range(chunk_count):
                logical_start = chunk_index * TRANSCRIPTION_CHUNK_SECONDS
                logical_end = min(duration, logical_start + TRANSCRIPTION_CHUNK_SECONDS)
                media_start = max(0.0, logical_start - TRANSCRIPTION_CHUNK_OVERLAP_SECONDS)
                media_end = min(duration, logical_end + TRANSCRIPTION_CHUNK_OVERLAP_SECONDS)
                chunk_ranges.append((chunk_index, chunk_count, logical_start, logical_end, media_start, media_end))
        else:
            chunk_ranges = [(0, 1, 0.0, duration or 0.0, 0.0, duration or 0.0)]

        _status(args, f"Whisper · transcription de {filename} en {len(chunk_ranges)} segment(s)…")
        track_segments: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="glimio-transcript-", dir=transcript_dir) as temp_dir:
            temp_path = Path(temp_dir)
            for chunk_index, chunk_count, logical_start, logical_end, media_start, media_end in chunk_ranges:
                source_path = audio_path
                if chunk_count > 1:
                    source_path = temp_path / f"audio_{chunk_index + 1:04d}.wav"
                    _extract_chunk(audio_path, source_path, media_start, media_end, str(getattr(args, "ffmpeg", "ffmpeg")), cancel_event)
                output_base = temp_path / f"{audio_path.stem}_{chunk_index + 1:04d}"
                _status(args, f"Whisper · {filename} · segment {chunk_index + 1}/{chunk_count}…")
                log(f"Transcribing {filename}, segment {chunk_index + 1}/{chunk_count}...")
                provider_segments = provider.transcribe(TranscriptionRequest(
                    audio_path=str(source_path),
                    model_path=str(model_path),
                    output_prefix=str(output_base),
                    language=args.language,
                    threads=args.threads,
                ))
                segments = [{
                    "start": item.start_seconds,
                    "end": item.end_seconds,
                    "speaker": source_name,
                    "source": source_name,
                    "text": item.text,
                } for item in provider_segments]
                for item in segments:
                    item["start"] += media_start
                    item["end"] += media_start
                # Adjacent chunks include a short overlap. Keep each recognized segment
                # only in the chunk containing its midpoint to avoid duplicate speech.
                if chunk_count > 1:
                    segments = [
                        item for item in segments
                        if logical_start <= (item["start"] + item["end"]) / 2 < logical_end
                    ]
                all_segments.extend(segments)
                track_segments.extend(segments)
                all_segments.sort(key=lambda item: (item["start"], item["end"]))
                track_segments.sort(key=lambda item: (item["start"], item["end"]))
                log(f"Read {len(segments)} segments from {filename} segment {chunk_index + 1}/{chunk_count}.")
                if all_segments:
                    _atomic_write_text(transcript_dir / "transcription_en_cours.md", _render_transcript(all_segments, in_progress=True))
                    _publish_artifact_update(args, "transcript")
        srt_lines: list[str] = []
        for index, item in enumerate(track_segments, start=1):
            srt_lines.extend([
                str(index),
                f"{_srt_stamp(item['start'])} --> {_srt_stamp(item['end'])}",
                str(item["text"]),
                "",
            ])
        _atomic_write_text(transcript_dir / f"{audio_path.stem}.srt", "\n".join(srt_lines))

    if tracks_found == 0:
        raise SystemExit(f"No supported audio track found in {folder}.")
    all_segments.sort(key=lambda item: (item["start"], item["end"]))
    if not all_segments:
        raise SystemExit("No transcript segments were found.")

    _status(args, "Whisper · fusion des segments et sauvegarde de la transcription…")
    json_path = transcript_output_path(folder, "transcription.json")
    json_path.write_text(
        json.dumps({"language": args.language, "language_mode": "automatic" if str(args.language).casefold() == "auto" else "forced", "segments": all_segments}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path = transcript_output_path(folder, "transcription.md")
    _atomic_write_text(markdown_path, _render_transcript(all_segments))
    (transcript_dir / "transcription_en_cours.md").unlink(missing_ok=True)
    # Fresh transcription invalidates diarization from an older transcript.
    transcript_output_path(folder, "speaker_diarization.json").unlink(missing_ok=True)
    log(f"Transcript created: {markdown_path}")
    log(f"JSON created: {json_path}")
    _status(args, "Transcription fusionnée et enregistrée")

    if getattr(args, "diarize", False):
        _status(args, "Détection des changements de voix…")
        diarize_transcription_isolated(
            folder,
            args,
            backup_existing=True,
            cancel_event=getattr(args, "_cancel_event", None),
        )
        _status(args, "Diarisation terminée")
        _publish_artifact_update(args, "transcript")
