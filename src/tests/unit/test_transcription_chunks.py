from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np
import pytest

from seance.processing import transcription
from seance.providers.contracts import MediaCancelled, MediaToolchainError, MediaToolchainUnavailable


def _write_pcm_wav(path: Path, *, rate: int = 8000, seconds: float = 2.0) -> bytes:
    frames = np.arange(int(rate * seconds), dtype="<i2").tobytes()
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(frames)
    return frames


def _wav_frames(path: Path) -> tuple[int, int, bytes]:
    with wave.open(str(path), "rb") as stream:
        return stream.getframerate(), stream.getnframes(), stream.readframes(stream.getnframes())


class _UnavailableMedia:
    def extract_chunk(self, request) -> None:
        raise MediaToolchainUnavailable("ffmpeg introuvable")


class _FailingMedia:
    def extract_chunk(self, request) -> None:
        raise MediaToolchainError("boom")


class _CancelledMedia:
    def extract_chunk(self, request) -> None:
        raise MediaCancelled("Traitement annulé.")


def test_extract_chunk_falls_back_to_native_wav_slicing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "audio_import.wav"
    frames = _write_pcm_wav(source, rate=8000, seconds=2.0)
    target = tmp_path / "chunk.wav"
    logs: list[str] = []

    monkeypatch.setattr(transcription, "log", logs.append)

    transcription._extract_chunk(source, target, 0.25, 1.25, _UnavailableMedia())

    rate, frame_count, data = _wav_frames(target)
    assert rate == 8000
    assert frame_count == 8000
    assert data == frames[2000 * 2:10000 * 2]
    assert logs and "découpage WAV natif" in logs[0]


def test_extract_chunk_enforces_a_minimum_duration_like_ffmpeg(tmp_path: Path) -> None:
    source = tmp_path / "audio_import.wav"
    _write_pcm_wav(source, rate=8000, seconds=2.0)
    target = tmp_path / "chunk.wav"

    transcription._extract_chunk(source, target, 1.0, 1.0, _UnavailableMedia())

    _, frame_count, _ = _wav_frames(target)
    assert frame_count == 800


def test_extract_chunk_does_not_fall_back_for_a_non_pcm_source(tmp_path: Path) -> None:
    source = tmp_path / "audio_import.wav"
    source.write_bytes(b"not a wave file")
    target = tmp_path / "chunk.wav"

    with pytest.raises(SystemExit):
        transcription._extract_chunk(source, target, 0.0, 1.0, _UnavailableMedia())
    assert not target.exists()


def test_extract_chunk_does_not_fall_back_a_missing_source(tmp_path: Path) -> None:
    target = tmp_path / "chunk.wav"

    with pytest.raises(SystemExit):
        transcription._extract_chunk(tmp_path / "absent.wav", target, 0.0, 1.0, _UnavailableMedia())
    assert not target.exists()


def test_extract_chunk_keeps_failing_for_a_provider_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "audio_import.wav"
    _write_pcm_wav(source)
    target = tmp_path / "chunk.wav"
    fallback_calls: list[tuple[Path, Path]] = []

    def native_fallback(source_path: Path, target_path: Path, *args, **kwargs) -> bool:
        fallback_calls.append((source_path, target_path))
        return True

    monkeypatch.setattr(transcription, "_extract_wav_chunk", native_fallback)

    with pytest.raises(SystemExit):
        transcription._extract_chunk(source, target, 0.0, 1.0, _FailingMedia())
    assert fallback_calls == []
    assert not target.exists()


def test_extract_chunk_propagates_cancellation_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "audio_import.wav"
    _write_pcm_wav(source)
    target = tmp_path / "chunk.wav"
    fallback_calls: list[bool] = []

    monkeypatch.setattr(
        transcription, "_extract_wav_chunk",
        lambda *args, **kwargs: fallback_calls.append(True) or True,
    )

    with pytest.raises(SystemExit, match="Traitement annulé"):
        transcription._extract_chunk(target=target, source=source, start=0.0, end=1.0, media=_CancelledMedia())
    assert fallback_calls == []


def test_extract_chunk_uses_the_selected_media_provider(tmp_path: Path) -> None:
    source = tmp_path / "audio_import.wav"
    _write_pcm_wav(source)
    target = tmp_path / "chunk.wav"
    received = []

    class _RecordingMedia:
        def extract_chunk(self, request) -> None:
            received.append(request)
            Path(request.target).write_bytes(b"chunk")

    transcription._extract_chunk(source, target, 1.0, 2.0, _RecordingMedia(), threading.Event())

    assert len(received) == 1
    assert received[0].source == str(source)
    assert received[0].start_seconds == 1.0
    assert received[0].end_seconds == 2.0


def test_extract_wav_chunk_honours_cancellation(tmp_path: Path) -> None:
    source = tmp_path / "audio_import.wav"
    _write_pcm_wav(source)
    target = tmp_path / "chunk.wav"
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(SystemExit, match="Traitement annulé"):
        transcription._extract_wav_chunk(source, target, 0.0, 1.0, cancel_event)
    assert not target.exists()


def test_extract_wav_chunk_returns_false_for_a_non_pcm_source(tmp_path: Path) -> None:
    source = tmp_path / "compressed.wav"
    source.write_bytes(b"not a wave file")

    assert transcription._extract_wav_chunk(source, tmp_path / "chunk.wav", 0.0, 1.0) is False
