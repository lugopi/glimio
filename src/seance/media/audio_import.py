"""Import audio/video files into the same durable session layout as recordings."""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from ..layout import ensure_session_layout, metadata_output_path
from ..providers.contracts import AudioTrackRequest
from ..providers.media_tools import create_media_provider, ensure_media_toolchain_ready


def import_audio_file(
    path: str | Path,
    directory: str | Path = "seances",
    *,
    media_provider: str = "ffmpeg",
    media_options: Mapping[str, Any] | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
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

    ``media_options`` defaults to the historical ``ffmpeg``/``ffprobe`` arguments so
    existing callers keep their behaviour; the selected provider owns decoding and
    conversion while normalization stays a business rule of this use case.
    """
    if not 0.0 <= float(max_gain_db) <= 30.0:
        raise ValueError("max_gain_db must be between 0 and 30 dB")
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Fichier audio/vidéo introuvable : {source}")
    if source.stat().st_size <= 0:
        raise RuntimeError(f"Le fichier audio/vidéo est vide : {source}")

    options = (
        {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
        if media_options is None
        else dict(media_options)
    )
    if media_provider == "ffmpeg":
        # Keep the historical keyword arguments meaningful even when a caller
        # forwards an empty provider-options mapping.
        options.setdefault("ffmpeg", ffmpeg)
        options.setdefault("ffprobe", ffprobe)
    media = create_media_provider(media_provider, options)
    # Fail before creating the session directory so a missing tool leaves no empty séance.
    ensure_media_toolchain_ready(media.info, options)

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
        stream_info = media.probe_audio_streams(str(source))
        for stream_number, stream in enumerate(stream_info, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Import annulé.")
            channels = max(1, int(stream.channels))
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
                media.extract_track(AudioTrackRequest(
                    source=str(source),
                    output=str(output),
                    stream_index=int(stream.stream_index),
                    audio_index=int(stream.audio_index),
                    channel=channel_number,
                    cancel_event=cancel_event,
                ))
                if not output.is_file() or output.stat().st_size <= 44:
                    raise RuntimeError(
                        f"Le provider média {media.info.id} n'a produit aucune piste exploitable "
                        f"pour le flux {stream_number}."
                    )

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
                    "stream_index": int(stream.stream_index),
                    "audio_index": int(stream.audio_index),
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
