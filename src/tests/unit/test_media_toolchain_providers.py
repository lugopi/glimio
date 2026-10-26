from __future__ import annotations

import array
import threading
import wave
from pathlib import Path

import numpy as np
import pytest

from seance.processing.transcription import _checkpoint_signature
from seance.providers import media_tools
from seance.providers.contracts import (
    AudioChunkRequest, AudioStreamInfo, AudioTrackRequest, MediaCancelled,
    MediaToolchainError, MediaToolchainUnavailable,
)
from seance.providers.media_tools import (
    FFmpegMediaToolchain, NativeMediaToolchain, create_media_provider,
    media_toolchain_provider_infos, media_toolchain_readiness, media_toolchain_status,
)


def _write_stereo_pcm16(path: Path, *, left: int, right: int, rate: int = 16000, samples: int = 1600) -> None:
    interleaved = np.empty(samples * 2, dtype="<i2")
    interleaved[0::2] = left
    interleaved[1::2] = right
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(interleaved.tobytes())


def _wav(path: Path) -> tuple[int, int, int, np.ndarray]:
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        rate = stream.getframerate()
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
    return channels, sample_width, rate, data


def test_media_catalog_exposes_ffmpeg_and_a_ready_native_backend() -> None:
    infos = {info.id: info for info in media_toolchain_provider_infos()}
    assert set(infos) == {"ffmpeg", "native"}
    assert infos["native"].task == "media"
    assert infos["native"].execution == "embedded"
    assert infos["native"].requires == ()
    ready, missing = media_toolchain_readiness(infos["native"], {}, ".")
    assert ready is True and missing == ()


def test_create_media_provider_builds_the_selected_adapter() -> None:
    assert isinstance(create_media_provider("ffmpeg", {"ffmpeg": "ffmpeg"}), FFmpegMediaToolchain)
    assert isinstance(create_media_provider("native"), NativeMediaToolchain)


def test_create_media_provider_rejects_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="Provider média inconnu"):
        create_media_provider("made-up-media", {})


def test_media_errors_keep_the_runtime_error_contract() -> None:
    assert issubclass(MediaToolchainError, RuntimeError)
    assert issubclass(MediaToolchainUnavailable, RuntimeError)
    assert issubclass(MediaCancelled, RuntimeError)


def test_native_provider_probes_a_stereo_pcm16_16k_wav(tmp_path: Path) -> None:
    source = tmp_path / "stereo.wav"
    _write_stereo_pcm16(source, left=1000, right=3000)

    streams = NativeMediaToolchain().probe_audio_streams(str(source))

    assert streams == [AudioStreamInfo(stream_index=0, audio_index=0, channels=2)]


def test_native_provider_refuses_a_wav_that_is_not_pcm16_16k(tmp_path: Path) -> None:
    source = tmp_path / "eight_khz.wav"
    _write_stereo_pcm16(source, left=1000, right=3000, rate=8000)

    with pytest.raises(MediaToolchainUnavailable) as raised:
        NativeMediaToolchain().probe_audio_streams(str(source))
    message = str(raised.value)
    assert "WAV PCM 16 bits à 16 kHz" in message
    assert "ffmpeg" not in message.casefold()


def test_native_provider_refuses_a_non_wav_container(tmp_path: Path) -> None:
    source = tmp_path / "compressed.mp3"
    source.write_bytes(b"not a wave file")

    with pytest.raises(MediaToolchainUnavailable):
        NativeMediaToolchain().probe_audio_streams(str(source))


def test_native_provider_extracts_each_channel_and_downmixes(tmp_path: Path) -> None:
    source = tmp_path / "stereo.wav"
    _write_stereo_pcm16(source, left=1000, right=3000)
    provider = NativeMediaToolchain()

    def extract(channel: int | None, name: str) -> Path:
        target = tmp_path / name
        provider.extract_track(AudioTrackRequest(
            source=str(source), output=str(target), stream_index=0, audio_index=0, channel=channel,
        ))
        return target

    channels, width, rate, first = _wav(target := extract(0, "first.wav"))
    assert (channels, width, rate) == (1, 2, 16000)
    assert set(first.tolist()) == {1000}

    _, _, _, second = _wav(extract(1, "second.wav"))
    assert set(second.tolist()) == {3000}

    _, _, _, mixed = _wav(extract(None, "mixed.wav"))
    assert set(mixed.tolist()) == {2000}


def test_native_downmix_keeps_the_historical_integer_average() -> None:
    samples = array.array("h", [32767, 32767, -32768, -32768, 1, 2, -1, -2, 1234, 4321])

    mixed = media_tools._downmix(samples, 2)

    assert isinstance(mixed, array.array)
    assert mixed.typecode == "h"
    # Truncating integer division is preserved, including for negative sums.
    assert mixed.tolist() == [32767, -32768, 1, -2, (1234 + 4321) // 2]


def test_native_downmix_matches_a_python_reference_on_long_blocks() -> None:
    rng = np.random.default_rng(1234)
    interleaved = rng.integers(-32768, 32768, size=16000 * 2, dtype=np.int16)
    expected = [
        (int(interleaved[index]) + int(interleaved[index + 1])) // 2
        for index in range(0, len(interleaved), 2)
    ]

    mixed = media_tools._downmix(array.array("h", interleaved.tobytes()), 2)

    assert mixed.tolist() == expected


def test_native_provider_rejects_an_out_of_range_channel(tmp_path: Path) -> None:
    source = tmp_path / "stereo.wav"
    _write_stereo_pcm16(source, left=1000, right=3000)

    with pytest.raises(MediaToolchainError, match="n'existe pas"):
        NativeMediaToolchain().extract_track(AudioTrackRequest(
            source=str(source), output=str(tmp_path / "bad.wav"),
            stream_index=0, audio_index=0, channel=2,
        ))


def test_native_provider_chunking_enforces_the_minimum_duration(tmp_path: Path) -> None:
    source = tmp_path / "stereo.wav"
    _write_stereo_pcm16(source, left=1000, right=3000, samples=16000)
    target = tmp_path / "chunk.wav"

    NativeMediaToolchain().extract_chunk(AudioChunkRequest(
        source=str(source), target=str(target), start_seconds=0.5, end_seconds=0.5,
    ))

    channels, width, rate, data = _wav(target)
    assert (channels, width, rate) == (2, 2, 16000)
    assert len(data) == 1600 * 2


def test_native_provider_chunking_honours_cancellation(tmp_path: Path) -> None:
    source = tmp_path / "stereo.wav"
    _write_stereo_pcm16(source, left=1000, right=3000)
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(MediaCancelled):
        NativeMediaToolchain().extract_chunk(AudioChunkRequest(
            source=str(source), target=str(tmp_path / "chunk.wav"),
            start_seconds=0.0, end_seconds=1.0, cancel_event=cancel_event,
        ))


def test_ffmpeg_provider_chunking_honours_cancellation_before_launching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"placeholder")
    cancel_event = threading.Event()
    cancel_event.set()
    monkeypatch.setattr("seance.providers.media_tools.resolve_command", lambda value, default=None: "/usr/bin/ffmpeg")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("FFmpeg must not be launched when cancellation is already requested")

    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", forbidden)

    with pytest.raises(MediaCancelled):
        FFmpegMediaToolchain({"ffmpeg": "ffmpeg"}).extract_chunk(AudioChunkRequest(
            source=str(source), target=str(tmp_path / "chunk.wav"),
            start_seconds=0.0, end_seconds=1.0, cancel_event=cancel_event,
        ))


def test_ffmpeg_provider_probes_streams_from_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "two_tracks.mkv"
    source.write_bytes(b"placeholder")
    payload = (
        '{"streams": [{"index": 2, "channels": 2}, {"index": 4, "channels": 1}]}'
    )

    class _Result:
        returncode = 0
        stdout = payload
        stderr = ""

    monkeypatch.setattr("seance.providers.media_tools.resolve_command", lambda value, default=None: "/usr/bin/ffmpeg")
    monkeypatch.setattr("seance.providers.media_tools.resolve_ffprobe", lambda *_args, **_kwargs: "/usr/bin/ffprobe")
    monkeypatch.setattr("seance.providers.media_tools.subprocess.run", lambda *args, **kwargs: _Result())

    streams = FFmpegMediaToolchain({"ffmpeg": "ffmpeg"}).probe_audio_streams(str(source))

    assert streams == [
        AudioStreamInfo(stream_index=2, audio_index=0, channels=2),
        AudioStreamInfo(stream_index=4, audio_index=1, channels=1),
    ]


def test_ffmpeg_readiness_exposes_resolved_executables(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"placeholder")
    ffprobe = tmp_path / "ffprobe.exe"
    ffprobe.write_bytes(b"placeholder")
    options = {"ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe)}

    ready, missing = media_toolchain_readiness(FFmpegMediaToolchain.info, options, tmp_path)
    missing, details = media_toolchain_status(FFmpegMediaToolchain.info, options, tmp_path)

    assert ready is True and missing == ()
    assert details["executable"] == str(ffmpeg.resolve())
    assert details["ffprobe_executable"] == str(ffprobe.resolve())


def test_checkpoint_signature_contains_the_media_provider_id_only(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    model = tmp_path / "model.bin"
    audio.write_bytes(b"audio")
    model.write_bytes(b"model")
    settings = {
        "provider_id": "whisper.cpp", "provider_options": {}, "model_path": model,
        "language": "fr", "threads": 2, "enhancement_provider": "no-enhancement",
        "enhancement_options": {}, "separation_provider": "no-separation",
        "separation_options": {}, "chunk_seconds": 15, "chunk_overlap_seconds": 0.0,
    }

    ffmpeg_signature = _checkpoint_signature(audio, media_provider="ffmpeg", **settings)
    native_signature = _checkpoint_signature(audio, media_provider="native", **settings)

    assert ffmpeg_signature != native_signature
    # An executable path is machine-specific and must not be part of the fingerprint;
    # only the provider identity is accepted.
    with pytest.raises(TypeError):
        _checkpoint_signature(
            audio, media_provider="ffmpeg", media_executable="C:/tools/ffmpeg.exe", **settings,
        )
