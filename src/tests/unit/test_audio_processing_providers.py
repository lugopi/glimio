from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from seance.processing.transcription import _checkpoint_signature, _contiguous_cached_chunks
from seance.providers import audio_processing
from seance.providers.audio_processing import (
    NO_EMBEDDING_INFO,
    SPEECHBRAIN_SEPARATION_INFO,
    SpeechBrainSepFormerProvider,
    create_audio_enhancement_provider,
    create_source_separation_provider,
    provider_readiness,
    verify_provider_dependencies,
)
from seance.providers.contracts import AudioEnhancementRequest


def test_no_embedding_provider_is_available_without_model_or_heavy_runtime() -> None:
    ready, missing = provider_readiness(NO_EMBEDDING_INFO, {})

    assert ready is True
    assert missing == ()


def test_sepformer_declares_and_enforces_hard_embedding_dependency() -> None:
    assert "speechbrain-ecapa" in SPEECHBRAIN_SEPARATION_INFO.requires
    with pytest.raises(RuntimeError, match="speechbrain-ecapa"):
        verify_provider_dependencies(
            SPEECHBRAIN_SEPARATION_INFO,
            available_provider_ids={"ffmpeg", "none-speaker-embedding"},
        )

    # The no-separation route remains usable without the optional dependency.
    provider = create_source_separation_provider(
        "no-separation", embedding_provider_id="none-speaker-embedding",
    )
    assert provider.info.id == "no-separation"


def test_source_identity_is_stable_when_sepformer_reverses_output_order(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SpeechBrainSepFormerProvider(
        {"identity_threshold": 0.62}, embedding_provider=SimpleNamespace(embed=lambda *_: np.ones(2)),
    )
    vectors = {
        0.1: np.asarray([1.0, 0.0], dtype=np.float32),
        0.2: np.asarray([0.0, 1.0], dtype=np.float32),
        0.3: np.asarray([-1.0, 0.0], dtype=np.float32),
    }
    monkeypatch.setattr(provider, "_voice_embedding", lambda samples: vectors[round(float(samples[0]), 1)])

    first = provider._assign_order([
        np.full(16_000, 0.1, dtype=np.float32),
        np.full(16_000, 0.2, dtype=np.float32),
    ])
    assert first[1] == ("speaker_00", "speaker_01")

    reversed_order = provider._assign_order([
        np.full(16_000, 0.2, dtype=np.float32),
        np.full(16_000, 0.1, dtype=np.float32),
    ])
    assert reversed_order[1] == ("speaker_01", "speaker_00")

    # A third person appearing later gets a new global ID; this is not a hard-coded
    # two-speaker diarization scheme across the entire session.
    third_person = provider._assign_order([
        np.full(16_000, 0.3, dtype=np.float32),
        np.full(16_000, 0.1, dtype=np.float32),
    ])
    assert third_person[1] == ("speaker_02", "speaker_00")

    state = provider.state_dict()
    restored = SpeechBrainSepFormerProvider(
        {"identity_threshold": 0.62}, embedding_provider=SimpleNamespace(embed=lambda *_: np.ones(2)),
    )
    restored.load_state_dict(state)
    assert restored.state_dict() == state



def test_ffmpeg_denoise_failure_points_to_ffmpeg_provider_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider = create_audio_enhancement_provider("ffmpeg-denoise")

    def failing_popen(*_args, **_kwargs):
        raise OSError("programme introuvable")

    monkeypatch.setattr(audio_processing.subprocess, "Popen", failing_popen)
    request = AudioEnhancementRequest(
        audio_path=str(tmp_path / "source.wav"),
        output_path=str(tmp_path / "enhanced" / "source.wav"),
        ffmpeg="C:/tools/ffmpeg/bin/ffmpeg.exe",
        options={"noise_reduction": "strong"},
    )

    with pytest.raises(RuntimeError) as error:
        provider.enhance(request)

    message = str(error.value)
    assert "configurez le provider FFmpeg dans les paramètres" in message
    assert "Aucune amélioration" in message


def test_transcription_checkpoint_reuses_only_a_contiguous_prefix() -> None:
    chunk_ranges = [
        (0, 3, 0.0, 10.0, 0.0, 11.0),
        (1, 3, 10.0, 20.0, 9.0, 21.0),
        (2, 3, 20.0, 25.0, 19.0, 25.0),
    ]
    raw = {
        "0": {"logical_start": 0.0, "logical_end": 10.0, "segments": [], "provider_state": {"schema_version": 2}},
        # Block 1 is missing but block 2 exists. Reusing block 2 would restore stale voice identities.
        "2": {"logical_start": 20.0, "logical_end": 25.0, "segments": [], "provider_state": {"schema_version": 2}},
    }
    assert list(_contiguous_cached_chunks(raw, chunk_ranges)) == ["0"]



def test_later_track_checkpoint_invalidates_when_prior_track_changes(tmp_path: Path) -> None:
    audio = tmp_path / "current.wav"
    prior = tmp_path / "prior.wav"
    model = tmp_path / "whisper.bin"
    audio.write_bytes(b"current")
    prior.write_bytes(b"first version of earlier track")
    model.write_bytes(b"model")
    settings = {
        "provider_id": "whisper.cpp", "provider_options": {}, "model_path": model,
        "language": "fr", "threads": 4, "enhancement_provider": "ffmpeg-denoise",
        "enhancement_options": {}, "separation_provider": "speechbrain-sepformer",
        "separation_options": {}, "chunk_seconds": 26, "chunk_overlap_seconds": 2.0,
        "identity_context_paths": [prior],
    }
    before = _checkpoint_signature(audio, **settings)
    prior.write_bytes(b"changed earlier track")
    after = _checkpoint_signature(audio, **settings)
    assert before != after
