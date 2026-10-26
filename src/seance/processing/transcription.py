from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import wave
from pathlib import Path
from typing import Any

from ..common import log
from ..layout import ensure_session_layout, get_audio_path, transcript_output_path
from ..media.audio_import import import_audio_file
from ..providers import DEFAULT_TRANSCRIPTION_PROVIDER, create_transcription_provider
from ..providers.audio_processing import (
    create_audio_enhancement_provider, create_source_separation_provider,
)
from ..providers.contracts import AudioChunkRequest, AudioEnhancementRequest, AudioSeparationRequest
from ..providers.contracts import TranscriptionRequest
from ..providers.contracts import MediaCancelled, MediaToolchainError, MediaToolchainUnavailable
from ..providers.media_tools import DEFAULT_MEDIA_PROVIDER, create_media_provider
from ..project_paths import discover_project_root
from ..session_paths import resolve_session
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


def _extract_wav_chunk(source: Path, target: Path, start: float, end: float,
                       cancel_event: Any = None) -> bool:
    """Copy a PCM WAV range natively; return False when the source is not a PCM WAV."""
    try:
        with wave.open(str(source), "rb") as reader:
            rate = reader.getframerate()
            if rate <= 0:
                return False
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            total_frames = reader.getnframes()
            start_frame = min(total_frames, max(0, int(start * rate)))
            end_frame = min(total_frames, max(start_frame, int(end * rate)))
            # Match the FFmpeg path, which always extracts at least 0.1 s when possible.
            minimum_frames = max(1, int(round(0.1 * rate)))
            end_frame = min(total_frames, max(end_frame, start_frame + minimum_frames))
            frame_count = max(0, end_frame - start_frame)
            reader.setpos(start_frame)
            data = reader.readframes(frame_count)
            if cancel_event is not None and cancel_event.is_set():
                raise SystemExit("Traitement annulé.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(target), "wb") as writer:
                writer.setparams((channels, sample_width, rate, frame_count, "NONE", "not compressed"))
                writer.writeframes(data)
        return target.is_file() and target.stat().st_size > 0
    except (OSError, wave.Error, EOFError):
        target.unlink(missing_ok=True)
        return False


def _extract_chunk(source: Path, target: Path, start: float, end: float, media: Any,
                   cancel_event: Any = None) -> None:
    """Extract a chunk through the selected media provider with a native WAV fallback.

    Only an unavailable toolchain triggers the native fallback. A cancelled operation
    and a provider that ran but failed stay fatal, so a broken conversion is never
    silently replaced by incomplete audio.
    """
    try:
        media.extract_chunk(AudioChunkRequest(
            source=str(source), target=str(target),
            start_seconds=start, end_seconds=end, cancel_event=cancel_event,
        ))
    except MediaCancelled as exc:
        raise SystemExit("Traitement annulé.") from exc
    except MediaToolchainUnavailable as exc:
        # FFmpeg could not even be launched (missing/corrupt executable) or the
        # backend does not support this source. A PCM WAV source can still be
        # chunked natively, without any external tool.
        if _extract_wav_chunk(source, target, start, end, cancel_event):
            log(f"Provider média indisponible ({exc}) ; découpage WAV natif pour {source.name}.")
            return
        raise SystemExit(
            f"Impossible de découper le segment audio de {source.name} : le provider média n'a pas pu "
            f"être utilisé ({exc}). Installez FFmpeg, configurez son chemin dans les paramètres, ou "
            "désactivez l'amélioration audio et la séparation des voix."
        ) from exc
    except MediaToolchainError as exc:
        raise SystemExit(f"Could not extract audio chunk from {source.name}: {exc}") from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise SystemExit(f"Could not extract audio chunk from {source.name}: empty output")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SystemExit(f"Could not write checkpoint {path}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _checkpoint_signature(
    audio_path: Path, *, provider_id: str, provider_options: dict[str, Any],
    model_path: Path, language: str, threads: int,
    enhancement_provider: str, enhancement_options: dict[str, Any],
    separation_provider: str, separation_options: dict[str, Any],
    chunk_seconds: int, chunk_overlap_seconds: float,
    media_provider: str = DEFAULT_MEDIA_PROVIDER,
    identity_context_paths: list[Path] | None = None,
) -> str:
    """Fingerprint source audio, model, and every setting that changes transcription."""
    audio_stat = audio_path.stat()
    try:
        model_stat = model_path.stat()
        model_signature: dict[str, Any] = {"size": model_stat.st_size, "mtime_ns": model_stat.st_mtime_ns}
    except OSError:
        model_signature = {"missing": str(model_path)}
    value = {
        "audio": {"path": str(audio_path.resolve()), "size": audio_stat.st_size, "mtime_ns": audio_stat.st_mtime_ns},
        "model": {"path": str(model_path.resolve()), **model_signature},
        "provider": provider_id, "provider_options": provider_options,
        # Only the provider identity is part of the fingerprint. An executable path
        # can differ between machines without changing the produced transcript.
        "media_provider": media_provider,
        "optional_assets": {
            "enhancement": _asset_signature(enhancement_options),
            "separation": _asset_signature(separation_options),
        },
        "language": language, "threads": threads,
        "enhancement_provider": enhancement_provider, "enhancement_options": enhancement_options,
        "separation_provider": separation_provider, "separation_options": separation_options,
        "pipeline_version": 5,
        "chunk_seconds": chunk_seconds,
        "chunk_overlap_seconds": chunk_overlap_seconds,
        # Separator speaker IDs are linked across tracks in a deterministic order.
        # A checkpoint for track N therefore depends on all earlier source tracks.
        "identity_context": [
            {"path": str(path.resolve()), "size": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}
            for path in (identity_context_paths or [])
        ],
    }
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_signature(value: Any) -> Any:
    """Fingerprint optional local model assets so replacing weights invalidates checkpoints."""
    if isinstance(value, dict):
        return {str(key): _asset_signature(item) for key, item in value.items()}
    if not isinstance(value, str) or not value.strip():
        return value
    candidate = Path(value).expanduser()
    if not (candidate.exists() and (candidate.is_file() or candidate.is_dir())):
        return value
    try:
        stat = candidate.stat()
        result: dict[str, Any] = {"path": str(candidate.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if candidate.is_dir():
            children = []
            for child in sorted(candidate.rglob("*")):
                if child.is_file() and ".glimio-runtime" not in child.parts:
                    child_stat = child.stat()
                    children.append((str(child.relative_to(candidate)), child_stat.st_size, child_stat.st_mtime_ns))
            result["files"] = children
        return result
    except OSError:
        return {"path": str(candidate), "unreadable": True}


def _load_track_checkpoint(path: Path, signature: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"signature": signature, "chunks": {}}
    if not isinstance(payload, dict) or payload.get("signature") != signature:
        return {"signature": signature, "chunks": {}}
    # Read both the legacy all-in-one file and the new small manifest referencing
    # one atomic JSON file per chunk (important when SepFormer creates hundreds of chunks).
    if isinstance(payload.get("chunks"), dict):
        return payload
    if payload.get("format") == "chunk-files-v1" and isinstance(payload.get("chunk_keys"), list):
        return payload
    return {"signature": signature, "chunks": {}}


def _contiguous_cached_chunks(raw_chunks: dict[str, Any], chunk_ranges: list[tuple[int, int, float, float, float, float]]) -> dict[str, Any]:
    """Return only the valid cache prefix; provider state depends on prior chunks."""
    valid: dict[str, Any] = {}
    for chunk_index, _count, logical_start, logical_end, _media_start, _media_end in chunk_ranges:
        cached = raw_chunks.get(str(chunk_index))
        if not isinstance(cached, dict) or not isinstance(cached.get("segments"), list):
            break
        try:
            cached_start = float(cached.get("logical_start", -1))
            cached_end = float(cached.get("logical_end", -1))
        except (TypeError, ValueError):
            break
        if abs(cached_start - logical_start) >= 0.001 or abs(cached_end - logical_end) >= 0.001:
            break
        provider_state = cached.get("provider_state")
        if provider_state is not None and not isinstance(provider_state, dict):
            break
        valid[str(chunk_index)] = cached
    return valid


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


def transcribe(args: argparse.Namespace) -> None:
    executable = Path(args.whisper_cli).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()
    raw_provider_options = getattr(args, "provider_options", {}) or {}
    if not isinstance(raw_provider_options, dict):
        raw_provider_options = {}
    media_provider_id = str(getattr(args, "media_provider", DEFAULT_MEDIA_PROVIDER) or DEFAULT_MEDIA_PROVIDER)
    saved_media_options = raw_provider_options.get(media_provider_id, {})
    media_options = dict(saved_media_options) if isinstance(saved_media_options, dict) else {}
    if media_provider_id == "ffmpeg":
        # Historical CLI flags and settings fields remain a compatibility alias.
        media_options.setdefault("ffmpeg", getattr(args, "ffmpeg", "ffmpeg") or "ffmpeg")
        media_options.setdefault("ffprobe", getattr(args, "ffprobe", "ffprobe") or "ffprobe")
    media = create_media_provider(media_provider_id, media_options)

    requested = getattr(args, "folder", None)
    if requested and Path(requested).expanduser().is_file():
        folder = import_audio_file(
            requested,
            getattr(args, "directory", "seances"),
            media_provider=media_provider_id,
            media_options=media_options,
            ffmpeg=getattr(args, "ffmpeg", "ffmpeg"),
            ffprobe=getattr(args, "ffprobe", "ffprobe"),
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
    provider_id = getattr(args, "transcription_provider", DEFAULT_TRANSCRIPTION_PROVIDER)
    saved_provider_options = raw_provider_options.get(provider_id, {})
    provider_options = dict(saved_provider_options) if isinstance(saved_provider_options, dict) else {}
    # Resolve every path declared by the selected provider. The provider metadata
    # distinguishes model/assets from executable commands that may be on PATH.
    project_root = discover_project_root(package_file=__file__)
    from ..providers import get_provider_info
    from ..providers.options import resolve_provider_option_paths
    transcription_info = get_provider_info(provider_id)
    if transcription_info is not None:
        for option in transcription_info.options:
            if option.key not in provider_options:
                if hasattr(args, option.key) and getattr(args, option.key) is not None:
                    provider_options[option.key] = getattr(args, option.key)
                else:
                    provider_options[option.key] = option.default
    provider_options = resolve_provider_option_paths(transcription_info, provider_options, project_root)
    # Explicit CLI flags take precedence over the saved provider settings.
    for arg_name, option_name in (("vad_mode", "vad_mode"), ("vad_model", "vad_model"), ("vad_threshold", "vad_threshold")):
        value = getattr(args, arg_name, None)
        if value is not None:
            provider_options[option_name] = value
    provider_options = resolve_provider_option_paths(transcription_info, provider_options, project_root)
    provider = create_transcription_provider(
        provider_id, executable, cancel_event=getattr(args, "_cancel_event", None), options=provider_options,
    )

    provider_options_all = raw_provider_options if isinstance(raw_provider_options, dict) else {}
    enhancement_provider_id = str(getattr(args, "audio_enhancement_provider", "") or "")
    legacy_enhancement_arg = getattr(args, "speech_enhancement", None)
    if legacy_enhancement_arg:
        # Older CLI flags remain supported but are translated into the provider chain.
        enhancement_provider_id = {"off": "no-enhancement", "ffmpeg": "ffmpeg-denoise", "deepfilter": "deepfilternet", "auto": "ffmpeg-denoise"}.get(str(legacy_enhancement_arg).casefold(), "ffmpeg-denoise")
    if not enhancement_provider_id:
        legacy_enhancement = str(provider_options.get("speech_enhancement", "auto")).casefold()
        enhancement_provider_id = {"off": "no-enhancement", "ffmpeg": "ffmpeg-denoise", "deepfilter": "deepfilternet", "auto": "ffmpeg-denoise"}.get(legacy_enhancement, "ffmpeg-denoise")
    enhancement_options = dict(provider_options_all.get(enhancement_provider_id, {}) or {})
    if enhancement_provider_id == "deepfilternet":
        for arg_name, option_name in (("deep_filter_executable", "deep_filter_executable"), ("deep_filter_model", "deep_filter_model")):
            value = getattr(args, arg_name, None)
            if value:
                enhancement_options[option_name] = value
    separation_provider_id = str(getattr(args, "source_separation_provider", "no-separation") or "no-separation")
    separation_options = dict(provider_options_all.get(separation_provider_id, {}) or {})
    embedding_provider_id = str(getattr(args, "speaker_embedding_provider", "speechbrain-ecapa") or "speechbrain-ecapa")
    embedding_options = dict(provider_options_all.get(embedding_provider_id, {}) or {})

    from ..providers.options import resolve_provider_option_paths
    from ..providers import get_provider_info
    provider_option_groups = (
        (enhancement_provider_id, enhancement_options),
        (separation_provider_id, separation_options),
        (embedding_provider_id, embedding_options),
    )
    for selected_id, options in provider_option_groups:
        info = get_provider_info(selected_id)
        if info is not None:
            for option in info.options:
                if option.key not in options:
                    options[option.key] = option.default
            options.update(resolve_provider_option_paths(info, options, project_root))
    # The provider chain is independent from ASR. Selecting a source separator also
    # injects its declared embedding-provider dependency for stable identities between
    # short processing chunks. The default is no-separation (no extra heavy runtime).
    enhancement_provider = create_audio_enhancement_provider(enhancement_provider_id, enhancement_options)
    separator_provider = create_source_separation_provider(
        separation_provider_id, separation_options,
        embedding_provider_id=embedding_provider_id,
        embedding_options=embedding_options,
    )
    if separation_provider_id != "no-separation":
        # One diarization-identity decision must correspond to one ASR input window.
        # A SepFormer output stem is only one speaker for a single model window; never
        # concatenate 30-second sub-windows with different identities into one 15-min file.
        separation_window_seconds = int(separation_options.get("chunk_seconds", 30))
        if not 10 <= separation_window_seconds <= 60:
            raise SystemExit("La fenêtre SepFormer doit être comprise entre 10 et 60 secondes.")
        chunk_overlap_seconds = min(2.0, max(0.0, (separation_window_seconds - 6.0) / 4.0))
        chunk_seconds = max(4, separation_window_seconds - int(math.ceil(2 * chunk_overlap_seconds)))
    else:
        chunk_seconds = TRANSCRIPTION_CHUNK_SECONDS
        chunk_overlap_seconds = TRANSCRIPTION_CHUNK_OVERLAP_SECONDS
    checkpoints_dir = transcript_dir / "checkpoints" / "transcription"
    for track_position, audio_path in enumerate(tracks):
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
            source_name = filename[:-4].replace("-ch", " canal ").replace("-", " ").replace("_", " ").title()
        tracks_found += 1
        duration = _audio_duration(audio_path)
        if duration is not None and duration > chunk_seconds:
            chunk_count = max(1, int(math.ceil(duration / chunk_seconds)))
            chunk_ranges = []
            for chunk_index in range(chunk_count):
                logical_start = chunk_index * chunk_seconds
                logical_end = min(duration, logical_start + chunk_seconds)
                media_start = max(0.0, logical_start - chunk_overlap_seconds)
                media_end = min(duration, logical_end + chunk_overlap_seconds)
                chunk_ranges.append((chunk_index, chunk_count, logical_start, logical_end, media_start, media_end))
        else:
            chunk_ranges = [(0, 1, 0.0, duration or 0.0, 0.0, duration or 0.0)]

        signature = _checkpoint_signature(
            audio_path, provider_id=provider_id, provider_options=provider_options,
            model_path=Path(provider_options.get("model", model_path)).expanduser(), language=str(args.language),
            threads=int(args.threads), enhancement_provider=enhancement_provider_id,
            enhancement_options=enhancement_options, separation_provider=separation_provider_id,
            separation_options={**separation_options, "embedding_provider": embedding_provider_id, "embedding_options": embedding_options},
            chunk_seconds=chunk_seconds, chunk_overlap_seconds=chunk_overlap_seconds,
            media_provider=media_provider_id,
            identity_context_paths=tracks[:track_position] if separation_provider_id != "no-separation" else [],
        )
        checkpoint_path = checkpoints_dir / f"{audio_path.stem}.json"
        checkpoint_chunks_dir = checkpoints_dir / f"{audio_path.stem}.chunks"
        checkpoint = _load_track_checkpoint(checkpoint_path, signature)
        using_chunk_files = checkpoint.get("format") == "chunk-files-v1"
        if using_chunk_files:
            raw_cached_chunks: dict[str, Any] = {}
            for key in checkpoint.get("chunk_keys", []):
                if not isinstance(key, str):
                    continue
                chunk_path = checkpoint_chunks_dir / f"chunk_{int(key):06d}.json" if key.isdigit() else None
                if chunk_path is None:
                    continue
                try:
                    entry = json.loads(chunk_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                    continue
                if isinstance(entry, dict) and entry.get("signature") == signature:
                    raw_cached_chunks[key] = {name: value for name, value in entry.items() if name != "signature"}
        else:
            # Migrate older all-in-one checkpoints on the next successful write.
            raw_cached_chunks = checkpoint.get("chunks", {})
        # Identity-provider state is sequential. Reuse only a contiguous prefix so a
        # missing/corrupt earlier block cannot leave later speaker centroids inconsistent.
        cached_chunks = _contiguous_cached_chunks(raw_cached_chunks, chunk_ranges)
        checkpoint = {"signature": signature, "format": "chunk-files-v1", "chunk_keys": list(cached_chunks)}
        # Migrate or trim stale manifests before doing more inference. Stale chunks
        # beyond a missing/corrupt block are not trusted because speaker IDs depend on
        # the sequential state from all preceding chunks.
        for key, entry in cached_chunks.items():
            chunk_path = checkpoint_chunks_dir / f"chunk_{int(key):06d}.json"
            if not using_chunk_files or not chunk_path.is_file():
                _atomic_write_json(chunk_path, {"signature": signature, **entry})
        if checkpoint_path.is_file():
            try:
                existing_manifest = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                existing_manifest = {}
        else:
            existing_manifest = {}
        if (existing_manifest.get("format") != "chunk-files-v1"
                or existing_manifest.get("chunk_keys") != list(cached_chunks)):
            _atomic_write_json(checkpoint_path, checkpoint)

        _status(args, f"Whisper · transcription de {filename} en {len(chunk_ranges)} segment(s)…")
        track_segments: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="glimio-transcript-", dir=transcript_dir) as temp_dir:
            temp_path = Path(temp_dir)
            for chunk_index, chunk_count, logical_start, logical_end, media_start, media_end in chunk_ranges:
                chunk_key = str(chunk_index)
                cached = cached_chunks.get(chunk_key)
                if isinstance(cached, dict) and abs(float(cached.get("logical_start", -1)) - logical_start) < 0.001 and abs(float(cached.get("logical_end", -1)) - logical_end) < 0.001 and isinstance(cached.get("segments"), list):
                    segments = [dict(item) for item in cached["segments"] if isinstance(item, dict)]
                    restore_state = getattr(separator_provider, "load_state_dict", None)
                    if callable(restore_state) and cached.get("provider_state") is not None:
                        restore_state(cached.get("provider_state"))
                    log(f"Reprise : bloc {chunk_index + 1}/{chunk_count} de {filename} déjà transcrit.")
                    all_segments.extend(segments)
                    track_segments.extend(segments)
                    all_segments.sort(key=lambda item: (item["start"], item["end"]))
                    track_segments.sort(key=lambda item: (item["start"], item["end"]))
                    continue

                source_path = audio_path
                if chunk_count > 1:
                    source_path = temp_path / f"audio_{chunk_index + 1:04d}.wav"
                    _extract_chunk(audio_path, source_path, media_start, media_end, media, cancel_event)

                # Noise reduction precedes source separation: separators trained on cleaner
                # mixtures usually fare better when persistent hum/fan noise has been reduced.
                processing_input = source_path
                if enhancement_provider_id != "no-enhancement":
                    enhanced_input = temp_path / f"{source_path.stem}_preprocessed.wav"
                    _status(args, f"Audio · amélioration de la voix · {filename} · segment {chunk_index + 1}/{chunk_count}…")
                    enhanced_result = enhancement_provider.enhance(AudioEnhancementRequest(
                        audio_path=str(source_path), output_path=str(enhanced_input),
                        ffmpeg=str(getattr(args, "ffmpeg", "ffmpeg")), cancel_event=cancel_event,
                        options=enhancement_options,
                    ))
                    processing_input = Path(enhanced_result.audio_path)
                    if enhanced_result.changed:
                        log(f"Audio enhancement for {source_path.name}: {enhanced_result.provider_id}.")

                asr_sources: list[tuple[Path, str, str | None]]
                if separation_provider_id != "no-separation":
                    _status(args, f"Audio · séparation des voix · {filename} · segment {chunk_index + 1}/{chunk_count}…")
                    separated = separator_provider.separate(AudioSeparationRequest(
                        audio_path=str(processing_input), output_directory=str(temp_path),
                        output_prefix=f"{audio_path.stem}_chunk_{chunk_index + 1:04d}",
                        ffmpeg=str(getattr(args, "ffmpeg", "ffmpeg")), cancel_event=cancel_event,
                        options=separation_options,
                    ))
                    asr_sources = []
                    for source_index, separated_path in enumerate(separated.audio_paths):
                        separated_file = Path(separated_path)
                        source_id = separated.source_ids[source_index] if source_index < len(separated.source_ids) else None
                        if not source_id:
                            # Don't ask ASR to invent words for a stem judged silent/noisy.
                            log(f"Source séparée ignorée (aucune voix fiable) : {separated_file.name}.")
                            continue
                        try:
                            speaker_number = int(source_id.rsplit("_", 1)[-1]) + 1
                            label = f"Speaker {speaker_number} (séparation audio)"
                        except (ValueError, IndexError):
                            label = f"Voix séparée {source_id}"
                        asr_sources.append((separated_file, label, source_id))
                else:
                    asr_sources = [(processing_input, source_name, None)]

                chunk_segments: list[dict[str, Any]] = []
                for source_for_asr, asr_source_name, separated_speaker_id in asr_sources:
                    transcription_path = source_for_asr
                    output_base = temp_path / f"{source_for_asr.stem}_transcript"
                    _status(args, f"Whisper · {source_for_asr.name} · segment {chunk_index + 1}/{chunk_count}…")
                    log(f"Transcribing {source_for_asr.name}, segment {chunk_index + 1}/{chunk_count}...")
                    provider_segments = provider.transcribe(TranscriptionRequest(
                        audio_path=str(transcription_path), model_path=str(model_path),
                        output_prefix=str(output_base), language=args.language, threads=args.threads,
                    ))
                    segments = [{
                        "start": item.start_seconds + media_start,
                        "end": item.end_seconds + media_start,
                        "speaker": asr_source_name,
                        "source": source_name,
                        "source_file": filename,
                        "text": item.text,
                        **({"speaker_id": separated_speaker_id, "speaker_origin": "source_separation"} if separated_speaker_id else {}),
                    } for item in provider_segments]
                    # Overlap chunks only provide context; keep each utterance in the logical
                    # block containing its midpoint, preventing repeated phrases at boundaries.
                    if chunk_count > 1:
                        segments = [item for item in segments if logical_start <= (item["start"] + item["end"]) / 2 < logical_end]
                    chunk_segments.extend(segments)

                all_segments.extend(chunk_segments)
                track_segments.extend(chunk_segments)
                all_segments.sort(key=lambda item: (item["start"], item["end"]))
                track_segments.sort(key=lambda item: (item["start"], item["end"]))
                # One atomic file per block avoids O(n²) manifest rewrites on a
                # four-hour session using 30-second source-separation windows.
                state_export = getattr(separator_provider, "state_dict", None)
                chunk_record = {
                    "logical_start": logical_start, "logical_end": logical_end,
                    "segments": chunk_segments,
                    "provider_state": state_export() if callable(state_export) else None,
                }
                checkpoint_chunks_dir.mkdir(parents=True, exist_ok=True)
                chunk_checkpoint_path = checkpoint_chunks_dir / f"chunk_{chunk_index:06d}.json"
                _atomic_write_json(chunk_checkpoint_path, {"signature": signature, **chunk_record})
                cached_chunks[chunk_key] = chunk_record
                checkpoint = {"signature": signature, "format": "chunk-files-v1", "chunk_keys": list(cached_chunks)}
                _atomic_write_json(checkpoint_path, checkpoint)
                log(f"Read {len(chunk_segments)} segments from {filename} segment {chunk_index + 1}/{chunk_count}.")
                _atomic_write_text(transcript_dir / "transcription_en_cours.md", _render_transcript(all_segments, in_progress=True))
                _publish_artifact_update(args, "transcript")

        # Per-source SRT is also written atomically after all chunks for this source finish.
        srt_lines: list[str] = []
        for index, item in enumerate(track_segments, start=1):
            srt_lines.extend([str(index), f"{_srt_stamp(item['start'])} --> {_srt_stamp(item['end'])}", str(item["text"]), ""])
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
