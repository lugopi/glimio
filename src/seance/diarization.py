"""Local speaker diarization using sherpa-onnx and timestamped Whisper segments."""
from __future__ import annotations

import argparse
import json
import shutil
import wave
from pathlib import Path
from typing import Any

import numpy as np

from .common import log
from .layout import get_audio_path, get_transcript_path, transcript_output_path


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read PCM WAV with the standard library and return normalized mono float32 audio."""
    try:
        with wave.open(str(path), "rb") as stream:
            channels = stream.getnchannels()
            width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frames = stream.readframes(stream.getnframes())
    except (OSError, wave.Error) as exc:
        raise SystemExit(f"Impossible de lire la piste audio pour la diarisation ({path}): {exc}") from exc
    if sample_rate <= 0 or channels <= 0:
        raise SystemExit(f"Piste WAV invalide pour la diarisation : {path}")
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
    return np.asarray(values, dtype=np.float32), sample_rate


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or not audio.size:
        return audio.astype(np.float32, copy=False)
    target_length = max(1, round(len(audio) * target_rate / source_rate))
    source_positions = np.arange(len(audio), dtype=np.float64)
    target_positions = np.linspace(0, max(0, len(audio) - 1), target_length, dtype=np.float64)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


def _combined_audio(folder: Path, target_rate: int) -> np.ndarray:
    tracks: list[np.ndarray] = []
    from .layout import list_enabled_audio_paths
    for path in list_enabled_audio_paths(folder):
        if not path.is_file():
            continue
        samples, sample_rate = _read_wav(path)
        samples = _resample(samples, sample_rate, target_rate)
        if samples.size:
            # Normalize each source modestly so a quiet microphone is not completely
            # hidden by loopback audio. Averaging avoids doubling the mixed signal.
            peak = float(np.max(np.abs(samples)))
            if peak > 1e-6:
                samples = samples / max(peak, 0.25)
            tracks.append(samples)
    if not tracks:
        raise SystemExit(f"Aucune piste WAV exploitable pour la diarisation dans {folder}.")
    length = max(map(len, tracks))
    mixed = np.zeros(length, dtype=np.float32)
    weights = np.zeros(length, dtype=np.float32)
    for samples in tracks:
        mixed[:len(samples)] += samples
        weights[:len(samples)] += 1.0
    np.divide(mixed, weights, out=mixed, where=weights > 0)
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 1.0:
        mixed /= peak
    return mixed


def _segment_speaker(start: float, end: float, diarized: list[Any]) -> int | None:
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
    return best_speaker if best_speaker is not None else nearest_speaker


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


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

    segmentation_model = Path(getattr(args, "diarization_segmentation_model", "models/diarization/segmentation/segmentation.onnx")).expanduser().resolve()
    embedding_model = Path(getattr(args, "diarization_embedding_model", "models/diarization/embedding/embedding.onnx")).expanduser().resolve()
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
    audio = _combined_audio(root, int(diarizer.sample_rate))
    if not audio.size:
        raise SystemExit("Les pistes audio sont vides : impossible de lancer la diarisation.")
    if cancel_event is not None and cancel_event.is_set():
        raise SystemExit("Traitement annulé.")
    detected = diarizer.process(audio).sort_by_start_time()
    if cancel_event is not None and cancel_event.is_set():
        raise SystemExit("Traitement annulé.")
    detected_segments = [
        {"start": float(item.start), "end": float(item.end), "speaker": int(item.speaker)}
        for item in detected if float(item.end) > float(item.start)
    ]
    if not detected_segments:
        raise SystemExit("Aucun tour de parole n'a été détecté. Vérifiez la qualité audio et les modèles ONNX.")

    speaker_ids = sorted({item["speaker"] for item in detected_segments})
    speaker_labels = {speaker_id: f"Speaker {index + 1}" for index, speaker_id in enumerate(speaker_ids)}
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
        except (TypeError, ValueError):
            continue
        speaker_id = _segment_speaker(start, end, detected_segments)
        if speaker_id is None:
            continue
        segment["speaker_id"] = f"speaker_{speaker_id:02d}"
        segment["speaker"] = speaker_labels[speaker_id]

    transcript_output_path(root, "speaker_diarization.json").write_text(
        json.dumps({"sample_rate": int(diarizer.sample_rate), "speakers": speaker_labels, "segments": detected_segments}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Diarisation terminée : {len(speaker_ids)} voix détectée(s), {len(detected_segments)} segments de voix.")
    return {"speakers": speaker_labels, "segments": detected_segments}
