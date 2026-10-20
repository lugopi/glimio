from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

from .audio_import import import_audio_file
from .common import log
from .layout import ensure_session_layout, get_audio_path, transcript_output_path
from .sessions import resolve_session
from .runtime import AI_ENGINE_LOCK

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


def _srt_seconds(stamp: str) -> float:
    stamp = stamp.strip().replace(".", ",")
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2}),(\d{1,3})", stamp)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {stamp!r}")
    hours, minutes, seconds, milliseconds = match.groups()
    milliseconds = milliseconds.ljust(3, "0")
    return (
        int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        + int(milliseconds) / 1000
    )


def _read_srt(path: Path, source: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"SRT file not found: {path}")

    raw = path.read_bytes()
    if not raw:
        return []
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = None
        for encoding in ("utf-8", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("latin-1")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    segments: list[dict[str, Any]] = []
    for block in re.split(r"\n[ \t]*\n+", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = re.fullmatch(
            r"\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
            r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})(?:\s+.*)?",
            lines[timing_index],
        )
        if not match:
            log(f"Ignoring invalid timestamp: {lines[timing_index]!r}", error=True)
            continue
        try:
            start = _srt_seconds(match.group(1))
            end = _srt_seconds(match.group(2))
        except ValueError as exc:
            log(str(exc), error=True)
            continue
        if end < start:
            log("Ignoring segment: end is before start.", error=True)
            continue
        content = " ".join(lines[timing_index + 1:]).strip()
        if content:
            segments.append({
                "start": start,
                "end": end,
                "speaker": source,
                "source": source,
                "text": content,
            })
    return segments


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


def _extract_chunk(source: Path, target: Path, start: float, end: float, ffmpeg: str) -> None:
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}",
        "-i", str(source), "-t", f"{max(0.1, end - start):.3f}", "-c", "copy", str(target),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
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


def _run_command(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    log(f"Waiting for the local AI engine slot: {Path(command[0]).name}")
    try:
        # Share the same process-local slot with llama.cpp. This prevents Whisper and
        # LLM model processes from competing for memory/CPU while still allowing capture.
        with AI_ENGINE_LOCK:
            log(f"Running: {Path(command[0]).name}")
            result = subprocess.run(
                command, cwd=str(cwd), capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False,
            )
    except OSError as exc:
        raise SystemExit(f"Could not run {command[0]}: {exc}") from exc

    if result.returncode != 0:
        log(f"Program failed (exit code {result.returncode}).", error=True)
        if result.stdout.strip():
            print(result.stdout[-12000:], file=sys.stderr, flush=True)
        if result.stderr.strip():
            print(result.stderr[-12000:], file=sys.stderr, flush=True)
        raise SystemExit(result.returncode)
    return result


def transcribe(args: argparse.Namespace) -> None:
    executable = Path(args.whisper_cli).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()
    if not executable.is_file():
        raise SystemExit(f"Whisper executable not found: {executable}")
    if not model_path.is_file():
        raise SystemExit(f"Whisper model not found: {model_path}")
    if args.threads < 1:
        raise SystemExit("--threads must be at least 1.")

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
    from .layout import list_audio_paths
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
    for audio_path in tracks:
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
                    _extract_chunk(audio_path, source_path, media_start, media_end, str(getattr(args, "ffmpeg", "ffmpeg")))
                output_base = temp_path / f"{audio_path.stem}_{chunk_index + 1:04d}"
                srt_path = output_base.with_suffix(".srt")
                command = [
                    str(executable), "-m", str(model_path), "-f", str(source_path),
                    "-l", args.language, "-osrt", "-of", str(output_base),
                    # Prefer more robust decoding over greedy speed, especially on long
                    # recordings where a bad phrase can otherwise reinforce later windows.
                    "-t", str(args.threads), "-bs", "5", "-mc", "512",
                ]
                if args.openvino_device:
                    command.extend(["--ov-e-device", args.openvino_device])
                _status(args, f"Whisper · {filename} · segment {chunk_index + 1}/{chunk_count}…")
                log(f"Transcribing {filename}, segment {chunk_index + 1}/{chunk_count}...")
                _run_command(command, cwd=folder)
                if not srt_path.is_file():
                    raise SystemExit(f"Expected SRT file was not created: {srt_path}")
                segments = _read_srt(srt_path, source_name)
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
        _status(args, "Diarisation · détection des changements de voix…")
        from .diarization import diarize_transcription

        diarize_transcription(folder, args, backup_existing=True)
        _status(args, "Diarisation terminée")
