"""Import audio/video files into the same durable session layout as recordings."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from ..layout import ensure_session_layout, metadata_output_path


def _ffprobe_for(ffmpeg: str) -> str | None:
    """Find ffprobe beside FFmpeg or on PATH; fail rather than silently discard tracks."""
    candidate = Path(ffmpeg).expanduser()
    if "/" in ffmpeg or "\\" in ffmpeg:
        sibling = candidate.with_name("ffprobe.exe" if candidate.suffix.lower() == ".exe" else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    found = shutil.which("ffprobe")
    if found and Path(found).name.casefold().startswith("ffprobe"):
        return found
    return None


def _audio_streams(source: Path, ffmpeg: str) -> list[dict[str, int]]:
    """Return audio-stream metadata without decoding the recording."""
    executable = _ffprobe_for(ffmpeg)
    if not executable:
        raise RuntimeError(
            "ffprobe est requis pour inspecter les pistes audio sans en perdre. "
            "Installez ffprobe depuis la même distribution que FFmpeg et réessayez."
        )
    command = [
        executable, "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index,channels", "-of", "json", str(source),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if result.returncode != 0:
            detail = (result.stderr or "aucun détail").strip()
            raise RuntimeError(f"Impossible d'inspecter les flux audio avec ffprobe : {detail[-2000:]}")
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams", []) if isinstance(payload, dict) else []
        discovered = [
            {"audio_index": index, "stream_index": int(item.get("index", index)), "channels": max(1, int(item.get("channels") or 1))}
            for index, item in enumerate(streams) if isinstance(item, dict)
        ]
        if not discovered:
            raise RuntimeError("Aucun flux audio exploitable n'a été trouvé dans ce fichier.")
        return discovered
    except RuntimeError:
        raise
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Impossible d'inspecter le fichier pour conserver toutes ses pistes audio : {exc}") from exc


def import_audio_file(
    path: str | Path,
    directory: str | Path = "seances",
    *,
    ffmpeg: str = "ffmpeg",
    normalize: bool = False,
    max_gain_db: float = 30.0,
    split_channels: bool = True,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Import every audio stream and preserve individual source channels by default.

    Each audio stream/channel becomes a separate mono PCM WAV, which keeps isolated
    microphone channels available to transcription and diarization instead of mixing
    them together at import time. Input gain is preserved by default so quiet noise does
    not get peak-amplified; set ``normalize=True`` for an explicit capped peak normalization.
    Set ``split_channels=False`` to downmix each stream.
    """
    if not 0.0 <= float(max_gain_db) <= 30.0:
        raise ValueError("max_gain_db must be between 0 and 30 dB")
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Fichier audio/vidéo introuvable : {source}")
    if source.stat().st_size <= 0:
        raise RuntimeError(f"Le fichier audio/vidéo est vide : {source}")

    executable = str(ffmpeg or "ffmpeg").strip() or "ffmpeg"
    has_path_separator = "/" in executable or "\\" in executable
    if has_path_separator and not Path(executable).expanduser().is_file():
        raise FileNotFoundError(f"Exécutable FFmpeg introuvable : {executable}")
    if not has_path_separator and shutil.which(executable) is None:
        raise FileNotFoundError(f"FFmpeg est introuvable dans le PATH : {executable}")

    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone()
    base_name = started.strftime("%Y-%m-%d_%H-%M-%S")
    folder = root / base_name
    suffix = 1
    while folder.exists():
        folder = root / f"{base_name}_{suffix:02d}"
        suffix += 1

    layout = ensure_session_layout(folder)
    audio_dir = layout["audio"]
    imported_tracks: list[dict[str, object]] = []
    try:
        stream_info = _audio_streams(source, executable)
        for stream_number, stream in enumerate(stream_info, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Import annulé.")
            channels = max(1, int(stream.get("channels", 1)))
            channel_numbers: list[int | None] = list(range(channels)) if split_channels and channels > 1 else [None]
            base_stem = "audio_import" if stream_number == 1 else f"audio_import-{stream_number}"
            for channel_number in channel_numbers:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Import annulé.")
                if channel_number is None or channel_number == 0:
                    filename = f"{base_stem}.wav"
                else:
                    filename = f"{base_stem}-ch{channel_number + 1}.wav"
                output = audio_dir / filename
                command = [
                    executable, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source), "-vn", "-map", f"0:a:{int(stream['audio_index'])}",
                ]
                if channel_number is not None:
                    command.extend(["-af", f"pan=mono|c0=c{channel_number}"])
                command.extend(["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)])
                try:
                    process = subprocess.Popen(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", errors="replace",
                    )
                except OSError as exc:
                    raise RuntimeError(f"Impossible de lancer FFmpeg pour la piste {stream_number} : {exc}") from exc
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        process.terminate()
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise RuntimeError("Import annulé.")
                    try:
                        stdout, stderr = process.communicate(timeout=0.25)
                        result = subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 44:
                    detail = (result.stderr or result.stdout or "aucune piste audio exploitable").strip()
                    label = f"flux {stream_number}" + (f", canal {channel_number + 1}" if channel_number is not None else "")
                    raise RuntimeError(f"Impossible de convertir le {label} avec FFmpeg : {detail[-3000:]}")

                # Normalize each independent channel, never combine the channels first.
                from .audio import _normalize_wav_peak
                normalization_info = _normalize_wav_peak(
                    output, enabled=normalize, max_gain_db=max_gain_db,
                )
                if channel_number is None:
                    track_name = "Audio importé" if stream_number == 1 else f"Audio importé {stream_number}"
                else:
                    track_name = ("Audio importé" if stream_number == 1 else f"Audio importé {stream_number}") + f" · Canal {channel_number + 1}"
                imported_tracks.append({
                    "filename": filename,
                    "name": track_name,
                    "kind": "import",
                    "stream_index": int(stream.get("stream_index", stream.get("audio_index", 0))),
                    "audio_index": int(stream["audio_index"]),
                    "source_channel": (channel_number + 1) if channel_number is not None else None,
                    "channels_in_source": channels,
                    "normalization": normalization_info,
                })

        if not imported_tracks:
            raise RuntimeError("Le fichier ne contient aucune piste audio exploitable.")
        metadata = {
            "title": source.stem.strip() or "Audio importé",
            "title_source": "filename",
            "started_at": started.isoformat(timespec="seconds"),
            "timezone": str(started.tzinfo),
            "source_filename": source.name,
            "source_type": source.suffix.lower().lstrip("."),
            "audio_bitrate_kbps": 256,
            "captured_tracks": [Path(str(item["filename"])).stem for item in imported_tracks],
            "audio_sources": imported_tracks,
            "audio_import_channel_mode": "split" if split_channels else "downmix",
            # Kept for older UI/builds that expect the legacy singular field.
            "audio_import_normalization": imported_tracks[0]["normalization"],
        }
        metadata_output_path(folder).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return folder
    except (OSError, RuntimeError):
        shutil.rmtree(folder, ignore_errors=True)
        raise
