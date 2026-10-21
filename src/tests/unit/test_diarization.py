from __future__ import annotations

import json
import sys
import types
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from seance.processing.diarization import diarize_transcription


def _write_wav(path: Path, samples: list[int], sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def _fake_sherpa(monkeypatch: pytest.MonkeyPatch) -> None:
    class Config:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def validate(self):
            return True

    class DiarizationResult(list):
        def sort_by_start_time(self):
            self.sort(key=lambda item: item.start)
            return self

    class Diarizer:
        sample_rate = 16000

        def __init__(self, config):
            self.config = config

        def process(self, audio):
            assert audio.dtype == np.float32
            assert audio.size > 0
            return DiarizationResult([
                SimpleNamespace(start=0.0, end=1.5, speaker=0),
                SimpleNamespace(start=1.5, end=3.0, speaker=1),
            ])

    module = types.SimpleNamespace(
        OfflineSpeakerDiarizationConfig=Config,
        OfflineSpeakerSegmentationModelConfig=Config,
        OfflineSpeakerSegmentationPyannoteModelConfig=Config,
        SpeakerEmbeddingExtractorConfig=Config,
        FastClusteringConfig=Config,
        OfflineSpeakerDiarization=Diarizer,
    )
    monkeypatch.setitem(sys.modules, "sherpa_onnx", module)


def test_diarization_aligns_speakers_and_keeps_original_transcript_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "session"
    (folder / "transcript").mkdir(parents=True)
    (folder / "models").mkdir()
    segmentation = folder / "models" / "segmentation.onnx"
    embedding = folder / "models" / "embedding.onnx"
    segmentation.touch()
    embedding.touch()
    _write_wav(folder / "audio" / "micro.wav", [1000, -1000] * 24000)
    transcript = {
        "language": "fr",
        "segments": [
            {"start": 0.2, "end": 1.0, "source": "Micro", "speaker": "Micro", "text": "Bonjour."},
            {"start": 1.8, "end": 2.6, "source": "Audio Windows", "speaker": "Audio Windows", "text": "Bonjour à tous."},
        ],
    }
    json_path = folder / "transcript" / "transcription.json"
    markdown_path = folder / "transcript" / "transcription.md"
    json_path.write_text(json.dumps(transcript), encoding="utf-8")
    markdown_path.write_text("# Original\n", encoding="utf-8")
    _fake_sherpa(monkeypatch)

    result = diarize_transcription(folder, SimpleNamespace(
        diarization_segmentation_model=str(segmentation),
        diarization_embedding_model=str(embedding),
        diarization_num_speakers=-1,
        diarization_threshold=0.5,
    ), backup_existing=True)

    updated = json.loads(json_path.read_text(encoding="utf-8"))
    diarization = json.loads((folder / "transcript" / "speaker_diarization.json").read_text(encoding="utf-8"))
    assert result["speakers"] == {0: "Speaker 1", 1: "Speaker 2"}
    assert updated["segments"][0]["speaker_id"] == "speaker_00"
    assert updated["segments"][0]["speaker"] == "Speaker 1"
    assert updated["segments"][1]["speaker"] == "Speaker 2"
    assert len(diarization["segments"]) == 2
    assert (folder / "transcript" / "transcription_before_diarization.json").is_file()
    assert (folder / "transcript" / "transcription_before_diarization.md").read_text(encoding="utf-8") == "# Original\n"
    assert "Speaker 1" in markdown_path.read_text(encoding="utf-8")


def test_diarization_fails_with_actionable_error_when_model_missing(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    (folder / "transcript").mkdir(parents=True)
    (folder / "transcript" / "transcription.json").write_text('{"segments": []}', encoding="utf-8")
    with pytest.raises(SystemExit, match="Modèle de diarisation segmentation introuvable"):
        diarize_transcription(folder, SimpleNamespace(
            diarization_segmentation_model=str(tmp_path / "missing-segmentation.onnx"),
            diarization_embedding_model=str(tmp_path / "missing-embedding.onnx"),
        ))
