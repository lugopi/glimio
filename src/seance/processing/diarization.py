"""Local speaker diarization using sherpa-onnx and timestamped Whisper segments."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import wave
from pathlib import Path
from typing import Any

import numpy as np

from ..common import log
from ..layout import get_transcript_path, transcript_output_path
from ..project_paths import discover_project_root

_RESAMPLE_CHUNK_SAMPLES = 1_000_000
DIARIZATION_CHUNK_SECONDS = 15 * 60
DIARIZATION_CHUNK_OVERLAP_SECONDS = 2.0


def _decode_pcm_frames(frames: bytes, width: int, channels: int, path: Path) -> np.ndarray:
    """Decode one bounded PCM frame block to mono float32 without retaining raw PCM bytes."""
    if width == 1:
        values = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        values = (values - 128.0) / 128.0
    elif width == 2:
        values = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        integers = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
        integers = np.where(integers & 0x800000, integers - 0x1000000, integers)
        values = integers.astype(np.float32) / 8388608.0
    elif width == 4:
        values = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise SystemExit(f"Format PCM WAV non pris en charge ({width * 8} bits) : {path}")
    if values.size % channels:
        values = values[: values.size - (values.size % channels)]
    if channels > 1:
        values = values.reshape(-1, channels).mean(axis=1)
    return np.asarray(values, dtype=np.float32)


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as stream:
            rate = stream.getframerate()
            return stream.getnframes() / rate if rate > 0 else 0.0
    except (OSError, wave.Error) as exc:
        raise SystemExit(f"Impossible de lire la durée audio ({path}) : {exc}") from exc


def _read_wav_range(path: Path, start_seconds: float, end_seconds: float, target_rate: int) -> np.ndarray:
    """Decode one bounded time window from a PCM WAV; never loads the full session."""
    try:
        with wave.open(str(path), "rb") as stream:
            channels = stream.getnchannels()
            width = stream.getsampwidth()
            source_rate = stream.getframerate()
            if source_rate <= 0 or channels <= 0:
                raise SystemExit(f"Piste WAV invalide pour la diarisation : {path}")
            start_frame = max(0, min(stream.getnframes(), int(start_seconds * source_rate)))
            end_frame = max(start_frame, min(stream.getnframes(), int(end_seconds * source_rate)))
            stream.setpos(start_frame)
            frames = stream.readframes(end_frame - start_frame)
    except (OSError, wave.Error) as exc:
        raise SystemExit(f"Impossible de lire une fenêtre de la piste audio ({path}) : {exc}") from exc
    samples = _decode_pcm_frames(frames, width, channels, path)
    return _resample(samples, source_rate, target_rate)


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator > 1e-8 else -1.0


def _model_fingerprint(path: Path) -> dict[str, Any]:
    """Fingerprint model files without hashing large weights on every job resume."""
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "missing": True}
    payload: dict[str, Any] = {
        "path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "is_dir": path.is_dir(),
    }
    if path.is_dir():
        files = []
        try:
            for child in sorted(path.rglob("*")):
                if child.is_file() and ".glimio-runtime" not in child.parts:
                    child_stat = child.stat()
                    files.append((str(child.relative_to(path)), child_stat.st_size, child_stat.st_mtime_ns))
        except OSError:
            return {**payload, "listing_error": True}
        payload["files"] = files
    return payload


def _diarization_signature(
    audio_paths: list[Path], segments: list[Any], *, segmentation_model: Path,
    embedding_model: Path, num_speakers: int, threshold: float,
    embedding_provider_id: str, embedding_options: dict[str, Any],
) -> str:
    """Invalidate cached diarization blocks whenever source audio/text/models/settings change."""
    transcript_input = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        transcript_input.append({key: item.get(key) for key in ("start", "end", "text", "source", "source_file")})
    payload = {
        "version": 2,
        "tracks": [_model_fingerprint(path) for path in audio_paths],
        "transcription_inputs": transcript_input,
        "segmentation_model": _model_fingerprint(segmentation_model),
        "embedding_model": _model_fingerprint(embedding_model),
        "num_speakers": num_speakers,
        "threshold": threshold,
        "chunk_seconds": DIARIZATION_CHUNK_SECONDS,
        "chunk_overlap_seconds": DIARIZATION_CHUNK_OVERLAP_SECONDS,
        "embedding_provider": embedding_provider_id,
        "embedding_options": embedding_options,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_diarization_checkpoint(path: Path, signature: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict) or payload.get("signature") != signature or not isinstance(payload.get("chunks"), dict):
        return {"signature": signature, "chunks": {}}
    return payload


def _write_diarization_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SystemExit(f"Impossible d'enregistrer le checkpoint de diarisation {path} : {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample mono audio to ``target_rate`` with chunked linear interpolation."""
    if source_rate == target_rate or not audio.size:
        return audio.astype(np.float32, copy=False)
    target_length = max(1, round(len(audio) * target_rate / source_rate))
    if target_length == 1:
        return audio[:1].astype(np.float32, copy=True)

    # Avoid allocating source and target position arrays for the entire recording.
    # Those float64 arrays, plus np.interp's output, can consume several GB for
    # long recordings and starve the API/UI while diarization prepares its input.
    output = np.empty(target_length, dtype=np.float32)
    scale = (len(audio) - 1) / (target_length - 1)
    last_source_index = len(audio) - 1
    for start in range(0, target_length, _RESAMPLE_CHUNK_SAMPLES):
        end = min(start + _RESAMPLE_CHUNK_SAMPLES, target_length)
        positions = np.arange(start, end, dtype=np.float64) * scale
        np.minimum(positions, last_source_index, out=positions)
        lower = positions.astype(np.intp)
        upper = np.minimum(lower + 1, last_source_index)
        fraction = (positions - lower).astype(np.float32)
        output[start:end] = audio[lower] + (audio[upper] - audio[lower]) * fraction
    return output


def _segment_speaker(start: float, end: float, diarized: list[Any]) -> int | None:
    """Pick the speaker with the largest overlap; use proximity only at a close boundary."""
    best_speaker: int | None = None
    best_overlap = 0.0
    midpoint = (start + end) / 2.0
    nearest_distance = float("inf")
    nearest_speaker: int | None = None
    for item in diarized:
        item_start = float(item["start"] if isinstance(item, dict) else item.start)
        item_end = float(item["end"] if isinstance(item, dict) else item.end)
        item_speaker = int(item["speaker"] if isinstance(item, dict) else item.speaker)
        overlap = max(0.0, min(end, item_end) - max(start, item_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = item_speaker
        distance = 0.0 if item_start <= midpoint <= item_end else min(abs(midpoint - item_start), abs(midpoint - item_end))
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_speaker = item_speaker
    if best_speaker is not None:
        return best_speaker
    # A far-away speaker turn must not be assigned to a transcript line during silence.
    # Tiny differences can come from word alignment/segmentation, so tolerate 300 ms.
    return nearest_speaker if nearest_distance <= 0.30 else None


def _format_timestamp(seconds: float) -> str:
    """Render a duration as a zero-padded HH:MM:SS stamp."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace a transcript file without exposing a half-written version."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SystemExit(f"Impossible d'écrire {path} : {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def diarize_transcription(folder: str | Path, args: argparse.Namespace, *, backup_existing: bool = False) -> dict[str, Any]:
    """Detect speaker turns and align them to Whisper's timestamped transcript."""
    cancel_event = getattr(args, "_cancel_event", None)
    if cancel_event is not None and cancel_event.is_set():
        raise SystemExit("Traitement annulé.")
    root = Path(folder).expanduser().resolve()
    json_path = get_transcript_path(root, "transcription.json")
    markdown_path = get_transcript_path(root, "transcription.md")
    if not json_path.is_file():
        raise SystemExit(f"Transcription horodatée introuvable : {json_path}. Relancez Whisper avant la diarisation.")

    project_root = discover_project_root(package_file=__file__)

    def resolve_project_path(value: str | Path) -> Path:
        raw = Path(value).expanduser()
        return (raw if raw.is_absolute() else project_root / raw).resolve()

    segmentation_model = resolve_project_path(getattr(args, "diarization_segmentation_model", "models/diarization/segmentation/segmentation.onnx"))
    embedding_model = resolve_project_path(getattr(args, "diarization_embedding_model", "models/diarization/embedding/embedding.onnx"))
    for label, path in (("segmentation", segmentation_model), ("embedding", embedding_model)):
        if not path.is_file():
            raise SystemExit(f"Modèle de diarisation {label} introuvable : {path}")

    try:
        import sherpa_onnx
    except ImportError as exc:
        raise SystemExit('La diarisation nécessite sherpa-onnx. Installez la dépendance avec : python -m pip install -e "[diarization]"') from exc

    try:
        transcript = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Impossible de lire la transcription JSON : {exc}") from exc
    segments = transcript.get("segments") if isinstance(transcript, dict) else None
    if not isinstance(segments, list) or not segments:
        raise SystemExit("La transcription JSON ne contient aucun segment horodaté à diariser.")
    nonempty_segments = [item for item in segments if isinstance(item, dict) and str(item.get("text", "")).strip()]
    separated_segments = [item for item in nonempty_segments if item.get("speaker_origin") == "source_separation"]
    if nonempty_segments and len(separated_segments) == len(nonempty_segments):
        # The selected separation provider has already linked voices between blocks
        # through its required embedding provider. Never overwrite the assignments by
        # diarizing the original mixed tracks again.
        if backup_existing:
            for original, backup_name in ((json_path, "transcription_before_diarization.json"), (markdown_path, "transcription_before_diarization.md")):
                backup = transcript_output_path(root, backup_name)
                if original.is_file() and not backup.exists():
                    shutil.copy2(original, backup)
        speaker_ids = sorted(
            {str(item.get("speaker_id")) for item in separated_segments if item.get("speaker_id")},
            key=lambda value: (int(value.rsplit("_", 1)[-1]) if value.rsplit("_", 1)[-1].isdigit() else 10**9, value),
        )
        labels = {}
        for source_id in speaker_ids:
            suffix = source_id.rsplit("_", 1)[-1]
            try:
                number = int(suffix) + 1
            except ValueError:
                number = len(labels) + 1
            labels[source_id] = f"Speaker {number} (séparation audio)"
        lines = ["# Transcription audio", "", "Les voix sont séparées par un modèle local. Vérifiez les passages superposés : les résultats dépendent du modèle et de l’enregistrement.", ""]
        separated_diarization_segments = []
        for item in nonempty_segments:
            source_id = str(item.get("speaker_id") or "")
            speaker_label = labels.get(source_id, str(item.get("speaker", "Speaker inconnu")))
            item["speaker"] = speaker_label
            try:
                start = float(item.get("start", 0))
                end = float(item.get("end", start))
            except (TypeError, ValueError):
                start, end = 0.0, 0.0
            try:
                numeric_speaker = int(source_id.rsplit("_", 1)[-1])
            except ValueError:
                numeric_speaker = -1
            separated_diarization_segments.append({
                "start": start, "end": end, "speaker": numeric_speaker,
                "speaker_id": source_id or None, "speaker_label": speaker_label,
                "track": str(item.get("source_file", "")),
            })
            lines.append(f"[{_format_timestamp(start)}–{_format_timestamp(end)}] **{speaker_label}**: {str(item.get('text', '')).strip()}")
        _atomic_write_text(markdown_path, "\n".join(lines) + "\n")
        _atomic_write_text(transcript_output_path(root, "speaker_diarization.json"), json.dumps({
            "provider": "source_separation", "speaker_identity_linking": "speaker-embedding-provider",
            "speakers": labels, "segments": separated_diarization_segments,
        }, ensure_ascii=False, indent=2) + "\n")
        _atomic_write_text(json_path, json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
        return {"speakers": labels, "segments": separated_diarization_segments, "provider": "source_separation"}

    if backup_existing:
        for original, backup_name in ((json_path, "transcription_before_diarization.json"), (markdown_path, "transcription_before_diarization.md")):
            backup = transcript_output_path(root, backup_name)
            if original.is_file() and not backup.exists():
                shutil.copy2(original, backup)

    num_speakers = int(getattr(args, "diarization_num_speakers", -1))
    threshold = float(getattr(args, "diarization_threshold", 0.5))
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation_model)),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding_model)),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers, threshold=threshold),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise SystemExit("Configuration sherpa-onnx invalide. Vérifiez les deux modèles ONNX de diarisation.")
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
    from ..layout import list_enabled_audio_paths
    audio_paths = [path for path in list_enabled_audio_paths(root) if path.is_file()]
    if not audio_paths:
        raise SystemExit(f"Aucune piste WAV exploitable pour la diarisation dans {root}.")

    # Optional global voice linker. The diarizer itself stays replaceable; ECAPA is
    # a separate provider and is activated only when its local model is available.
    provider_options = getattr(args, "provider_options", {}) or {}
    embedding_provider_id = str(getattr(args, "speaker_embedding_provider", "speechbrain-ecapa") or "speechbrain-ecapa")
    embedding_options = dict(provider_options.get(embedding_provider_id, {}) or {}) if isinstance(provider_options, dict) else {}
    for option_name, value in list(embedding_options.items()):
        if isinstance(value, str) and value.strip() and (option_name.endswith(("_dir", "_model", "_executable")) or option_name == "model_dir"):
            embedding_options[option_name] = str(resolve_project_path(value))
    embedding_provider = None
    if embedding_provider_id not in {"", "none"}:
        from ..providers.audio_processing import create_speaker_embedding_provider, provider_readiness, SPEECHBRAIN_EMBEDDING_INFO
        ready, missing = provider_readiness(SPEECHBRAIN_EMBEDDING_INFO, embedding_options)
        if ready:
            try:
                embedding_provider = create_speaker_embedding_provider(embedding_provider_id, embedding_options)
            except (ValueError, RuntimeError):
                embedding_provider = None

    # Build a deterministic plan of track/window jobs. Each completed window is
    # persisted with its turns and global identity state, so a four-hour diarization
    # resumes from the first incomplete window instead of starting over.
    plan: list[dict[str, Any]] = []
    total_windows = 0
    for track_index, path in enumerate(audio_paths):
        duration = _wav_duration(path)
        window_count = max(1, int(np.ceil(duration / DIARIZATION_CHUNK_SECONDS)))
        total_windows += window_count
        for window_index in range(window_count):
            logical_start = window_index * DIARIZATION_CHUNK_SECONDS
            logical_end = min(duration, logical_start + DIARIZATION_CHUNK_SECONDS)
            plan.append({
                "key": f"{track_index}:{window_index}", "track_index": track_index,
                "path": path, "duration": duration, "window_count": window_count,
                "window_index": window_index, "logical_start": logical_start,
                "logical_end": logical_end,
                "media_start": max(0.0, logical_start - DIARIZATION_CHUNK_OVERLAP_SECONDS),
                "media_end": min(duration, logical_end + DIARIZATION_CHUNK_OVERLAP_SECONDS),
            })

    signature = _diarization_signature(
        audio_paths, segments, segmentation_model=segmentation_model,
        embedding_model=embedding_model, num_speakers=num_speakers, threshold=threshold,
        embedding_provider_id=embedding_provider_id, embedding_options=embedding_options,
    )
    checkpoint_path = transcript_output_path(root, "checkpoints/diarization/state.json")
    raw_checkpoint = _load_diarization_checkpoint(checkpoint_path, signature)
    raw_chunks = raw_checkpoint.get("chunks", {})
    # Only reuse a contiguous prefix. If any block is missing/corrupt, later snapshots
    # depend on an identity history that we can no longer prove, so recompute the tail.
    cached_chunks: dict[str, Any] = {}
    for item in plan:
        cached = raw_chunks.get(item["key"])
        if not isinstance(cached, dict) or not isinstance(cached.get("turns"), list) or not isinstance(cached.get("identity_state"), dict):
            break
        state = cached["identity_state"]
        vectors, ids, counts = state.get("centroids"), state.get("centroid_ids"), state.get("counts")
        if not isinstance(vectors, list) or not isinstance(ids, list) or not isinstance(counts, list) or not (len(vectors) == len(ids) == len(counts)):
            break
        try:
            parsed_vectors = [np.asarray(vector, dtype=np.float32) for vector in vectors]
            parsed_ids = [int(value) for value in ids]
            parsed_counts = [int(value) for value in counts]
            valid_state = all(vector.ndim == 1 and vector.size and np.all(np.isfinite(vector)) for vector in parsed_vectors)
            valid_state = valid_state and all(value >= 1 for value in parsed_counts)
            valid_state = valid_state and isinstance(state.get("next_id"), int) and int(state["next_id"]) >= 0
        except (TypeError, ValueError):
            valid_state = False
        if not valid_state:
            break
        cached_chunks[item["key"]] = cached
    checkpoint: dict[str, Any] = {"signature": signature, "chunks": dict(cached_chunks)}

    local_turns: list[dict[str, Any]] = []
    global_centroids: list[np.ndarray] = []
    global_centroid_ids: list[int] = []
    global_counts: list[int] = []
    global_next_id = 0
    track_lookup = {path.name: path for path in audio_paths}
    source_to_filename = {"Micro": "micro.wav", "Audio Windows": "windows.wav", "Audio importé": "audio_import.wav"}
    processed_windows = 0
    for item in plan:
        if cancel_event is not None and cancel_event.is_set():
            raise SystemExit("Traitement annulé.")
        key = item["key"]
        cached = cached_chunks.get(key)
        if cached is not None:
            local_turns.extend(dict(turn) for turn in cached["turns"] if isinstance(turn, dict))
            state = cached["identity_state"]
            global_centroids = [np.asarray(vector, dtype=np.float32) for vector in state.get("centroids", [])]
            global_centroid_ids = [int(value) for value in state.get("centroid_ids", [])]
            global_counts = [max(1, int(value)) for value in state.get("counts", [])]
            global_next_id = int(state.get("next_id", 0))
            processed_windows += 1
            if callable(getattr(args, "status_callback", None)):
                try:
                    args.status_callback(f"Diarisation · {item['path'].name} · bloc {item['window_index'] + 1}/{item['window_count']} ({processed_windows}/{total_windows}) · repris")
                except Exception:
                    pass
            continue

        path: Path = item["path"]
        track_index = int(item["track_index"])
        window_index = int(item["window_index"])
        window_count = int(item["window_count"])
        logical_start = float(item["logical_start"])
        logical_end = float(item["logical_end"])
        media_start = float(item["media_start"])
        media_end = float(item["media_end"])
        samples = _read_wav_range(path, media_start, media_end, int(diarizer.sample_rate))
        chunk_turns: list[dict[str, Any]] = []
        if samples.size:
            detected = diarizer.process(samples).sort_by_start_time()
            local_segments = [
                {"start": float(turn.start), "end": float(turn.end), "speaker": int(turn.speaker)}
                for turn in detected if float(turn.end) > float(turn.start)
            ]
            # Keep turns in the logical block containing their midpoint; overlap is context only.
            local_segments = [turn for turn in local_segments if
                              logical_start <= media_start + (turn["start"] + turn["end"]) / 2 < logical_end]
            local_speakers = sorted({turn["speaker"] for turn in local_segments})
            speaker_embeddings: dict[int, np.ndarray] = {}
            if embedding_provider is not None and local_segments:
                for local_speaker in local_speakers:
                    candidates = sorted(
                        (turn for turn in local_segments if turn["speaker"] == local_speaker and turn["end"] - turn["start"] >= 0.8),
                        key=lambda turn: turn["end"] - turn["start"], reverse=True,
                    )[:3]
                    vectors: list[np.ndarray] = []
                    for turn in candidates:
                        left = max(0, int(turn["start"] * int(diarizer.sample_rate)))
                        right = min(len(samples), int(turn["end"] * int(diarizer.sample_rate)))
                        if right - left < int(0.6 * int(diarizer.sample_rate)):
                            continue
                        try:
                            vector = embedding_provider.embed(samples[left:right], int(diarizer.sample_rate))
                            if vector.size and np.all(np.isfinite(vector)) and float(np.linalg.norm(vector)) > 1e-6:
                                vectors.append(vector)
                        except Exception as exc:
                            log(f"Embedding de locuteur indisponible pour {path.name} (fallback sans rapprochement global) : {exc}")
                            embedding_provider = None
                            speaker_embeddings.clear()
                            break
                    if vectors:
                        mean = np.mean(np.stack(vectors), axis=0)
                        norm = float(np.linalg.norm(mean))
                        if norm > 0 and np.all(np.isfinite(mean)):
                            speaker_embeddings[local_speaker] = mean / norm

            local_to_global: dict[int, int] = {}
            for local_speaker in local_speakers:
                vector = speaker_embeddings.get(local_speaker)
                if vector is not None and global_centroids:
                    scores = [_cosine_similarity(vector, centroid) for centroid in global_centroids]
                    centroid_index = int(np.argmax(scores))
                    if scores[centroid_index] >= float(getattr(args, "speaker_embedding_threshold", 0.62)):
                        local_to_global[local_speaker] = global_centroid_ids[centroid_index]
                        global_counts[centroid_index] += 1
                        alpha = 1.0 / global_counts[centroid_index]
                        merged = (1.0 - alpha) * global_centroids[centroid_index] + alpha * vector
                        norm = float(np.linalg.norm(merged))
                        global_centroids[centroid_index] = merged / norm if norm > 0 else merged
                        continue
                global_id = global_next_id
                global_next_id += 1
                local_to_global[local_speaker] = global_id
                if vector is not None:
                    global_centroids.append(vector.copy())
                    global_centroid_ids.append(global_id)
                    global_counts.append(1)
                chunk_turns.append({"track": path.name, "track_index": track_index, "window_index": window_index,
                                    "window_start": logical_start, "local_speakers": len(local_speakers),
                                    "global_speaker": global_id, "embedding_linked": vector is not None})
            for turn in local_segments:
                chunk_turns.append({
                    "start": round(media_start + turn["start"], 3),
                    "end": round(media_start + turn["end"], 3),
                    "speaker": local_to_global[turn["speaker"]],
                    "track": path.name,
                    "window_index": window_index,
                })
        local_turns.extend(chunk_turns)
        state = {
            "centroids": [vector.astype(np.float32).tolist() for vector in global_centroids],
            "centroid_ids": list(global_centroid_ids), "counts": list(global_counts), "next_id": global_next_id,
        }
        checkpoint["chunks"][key] = {"turns": chunk_turns, "identity_state": state}
        _write_diarization_checkpoint(checkpoint_path, checkpoint)
        processed_windows += 1
        if callable(getattr(args, "status_callback", None)):
            try:
                args.status_callback(f"Diarisation · {path.name} · bloc {window_index + 1}/{window_count} ({processed_windows}/{total_windows})…")
            except Exception:
                pass

    detected_segments = [item for item in local_turns if "start" in item and "end" in item and "speaker" in item]
    if not detected_segments:
        raise SystemExit("Aucun tour de parole n'a été détecté. Vérifiez la qualité audio et les modèles ONNX.")
    speaker_ids = sorted({int(item["speaker"]) for item in detected_segments})
    speaker_labels = {speaker_id: f"Speaker {index + 1}" for index, speaker_id in enumerate(speaker_ids)}
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
        except (TypeError, ValueError):
            continue
        source_filename = str(segment.get("source_file") or "")
        if source_filename not in track_lookup:
            source_name = str(segment.get("source", ""))
            guessed = source_to_filename.get(source_name, "")
            source_filename = guessed if guessed in track_lookup else ""
        candidates = [item for item in detected_segments if item["track"] == source_filename] if source_filename else detected_segments
        speaker_id = _segment_speaker(start, end, candidates)
        if speaker_id is None:
            continue
        segment["speaker_id"] = f"speaker_{speaker_id:02d}"
        segment["speaker"] = speaker_labels[speaker_id]

    lines = ["# Transcription audio", "", "Les étiquettes Speaker indiquent les voix détectées automatiquement. Elles ne permettent pas d'identifier nominativement les personnes.", ""]
    for segment in segments:
        if not isinstance(segment, dict) or not str(segment.get("text", "")).strip():
            continue
        try:
            start = _format_timestamp(float(segment.get("start", 0)))
            end = _format_timestamp(float(segment.get("end", 0)))
        except (TypeError, ValueError):
            start, end = "00:00:00", "00:00:00"
        speaker = str(segment.get("speaker", segment.get("source", "Speaker inconnu")))
        lines.append(f"[{start}–{end}] **{speaker}**: {str(segment['text']).strip()}")
    # Write the source of truth (transcription.json) last: if the isolated
    # process is cancelled mid-write, the next run sees no speaker_id and redoes
    # the alignment instead of reusing a partially updated session.
    _atomic_write_text(markdown_path, "\n".join(lines) + "\n")
    _atomic_write_text(
        transcript_output_path(root, "speaker_diarization.json"),
        json.dumps({"sample_rate": int(diarizer.sample_rate), "chunk_seconds": DIARIZATION_CHUNK_SECONDS,
                    "speaker_identity_linking": "speechbrain-ecapa" if any(item.get("embedding_linked") for item in local_turns) else "track-and-window-scoped (no usable embedding model/results)",
                    "speakers": speaker_labels, "tracks": sorted({item["track"] for item in detected_segments}),
                    "segments": detected_segments}, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(json_path, json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
    log(f"Diarisation terminée : {len(speaker_ids)} voix détectée(s), {len(detected_segments)} segments de voix.")
    return {"speakers": speaker_labels, "segments": detected_segments}
