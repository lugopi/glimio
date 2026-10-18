"""Import audio/video files into the same durable session layout as recordings."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .layout import ensure_session_layout, metadata_output_path


def import_audio_file(path: str | Path, directory: str | Path = "seances", *, ffmpeg: str = "ffmpeg") -> Path:
    """Convert an audio/video source to a mono PCM WAV and return its session folder."""
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
    output = layout["audio"] / "audio_import.wav"
    command = [
        executable, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(output),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 44:
            detail = (result.stderr or result.stdout or "aucune piste audio exploitable").strip()
            raise RuntimeError(f"Impossible de convertir le fichier avec FFmpeg : {detail[-3000:]}")
        metadata = {
            "title": source.stem.strip() or "Audio importé",
            "title_source": "filename",
            "started_at": started.isoformat(timespec="seconds"),
            "timezone": str(started.tzinfo),
            "source_filename": source.name,
            "source_type": source.suffix.lower().lstrip("."),
            "audio_bitrate_kbps": 256,
            "captured_tracks": ["audio_import"],
        }
        metadata_output_path(folder).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return folder
    except (OSError, RuntimeError):
        shutil.rmtree(folder, ignore_errors=True)
        raise
