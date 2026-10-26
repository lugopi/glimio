from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from seance.media.audio_import import import_audio_file
from seance.providers.contracts import AudioStreamInfo


@pytest.fixture(autouse=True)
def _default_probe_reports_one_audio_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    # Individual import tests focus on conversion/normalization, not probing itself.
    monkeypatch.setattr(
        "seance.providers.media_tools.FFmpegMediaToolchain.probe_audio_streams",
        lambda _self, _source: [AudioStreamInfo(stream_index=0, audio_index=0, channels=1)],
    )
    # The media-tool preflight has its own dedicated tests below.
    monkeypatch.setattr(
        "seance.media.audio_import.ensure_media_toolchain_ready",
        lambda *_args, **_kwargs: None,
    )
    # Fake Popen tests must not depend on a real FFmpeg installation.
    monkeypatch.setattr(
        "seance.providers.media_tools.resolve_command",
        lambda value, default=None: "/usr/bin/ffmpeg",
    )


class FakeProcess:
    """Stand-in for the FFmpeg subprocess spawned by ``import_audio_file``.

    Behaves like an already-finished process: ``communicate`` writes the WAV
    fixture (via ``on_output`` when provided) and returns immediately.
    """

    def __init__(self, command, on_output=None, returncode=0, stdout="", stderr=""):
        self.command = command
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._on_output = on_output

    def communicate(self, timeout=None):
        if self.returncode == 0 and self._on_output is not None:
            self._on_output(self.command)
        return self._stdout, self._stderr

    def terminate(self):
        pass

    def kill(self):
        pass


def make_fake_popen(on_output=None, returncode=0, stdout="", stderr="", calls=None):
    def fake_popen(command, *args, **kwargs):
        if calls is not None:
            calls.append(command)
        return FakeProcess(command, on_output=on_output, returncode=returncode, stdout=stdout, stderr=stderr)

    return fake_popen


def write_silence_wav(command):
    output = Path(command[-1])
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * 100)


def write_quiet_wav(command):
    import numpy as np

    output = Path(command[-1])
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(np.full(1600, 1000, dtype="<i2").tobytes())


def test_import_audio_converts_to_durable_session_and_writes_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "Point équipe.mp4"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"
    calls = []

    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(on_output=write_silence_wav, calls=calls))
    result = import_audio_file(source, sessions, ffmpeg="ffmpeg")

    assert result.parent == sessions
    assert (result / "audio" / "audio_import.wav").is_file()
    assert calls[0][calls[0].index("-ar") + 1] == "16000"
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "Point équipe"
    assert metadata["source_filename"] == source.name
    assert metadata["captured_tracks"] == ["audio_import"]
    assert metadata["audio_import_normalization"]["status"] == "silence"


def test_import_audio_removes_partial_session_when_ffmpeg_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "broken.wav"
    source.write_bytes(b"not a real wav")
    sessions = tmp_path / "sessions"
    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(returncode=1, stderr="decode failed"))

    with pytest.raises(RuntimeError, match="decode failed"):
        import_audio_file(source, sessions, ffmpeg="ffmpeg")
    assert list(sessions.iterdir()) == []


def test_import_audio_applies_shared_peak_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "quiet-audio.mp3"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"

    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(on_output=write_quiet_wav))
    result = import_audio_file(source, sessions, ffmpeg="ffmpeg", normalize=True, max_gain_db=30)

    from seance.media.audio import _wav_pcm16_stats
    stats = _wav_pcm16_stats(result / "audio" / "audio_import.wav")
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["audio_import_normalization"]["status"] == "normalized"
    assert stats["peak_dbfs"] == pytest.approx(-6.0, abs=0.1)


def test_import_audio_preserves_quiet_input_gain_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "quiet-audio.mp3"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"

    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(on_output=write_quiet_wav))
    result = import_audio_file(source, sessions, ffmpeg="ffmpeg")

    from seance.media.audio import _wav_pcm16_stats
    stats = _wav_pcm16_stats(result / "audio" / "audio_import.wav")
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["audio_import_normalization"]["enabled"] is False
    assert metadata["audio_import_normalization"]["status"] == "disabled"
    assert stats["peak_dbfs"] == pytest.approx(-30.3, abs=0.2)


def test_import_audio_respects_disabled_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "quiet-audio.mp3"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"

    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(on_output=write_quiet_wav))
    result = import_audio_file(source, sessions, ffmpeg="ffmpeg", normalize=False, max_gain_db=30)

    from seance.media.audio import _wav_pcm16_stats
    stats = _wav_pcm16_stats(result / "audio" / "audio_import.wav")
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["audio_import_normalization"]["status"] == "disabled"
    assert stats["peak_dbfs"] == pytest.approx(-30.3, abs=0.2)


def test_import_audio_preserves_multiple_audio_streams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "multitrack.mkv"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"
    calls = []

    monkeypatch.setattr(
        "seance.providers.media_tools.FFmpegMediaToolchain.probe_audio_streams",
        lambda _self, _source: [
            AudioStreamInfo(stream_index=0, audio_index=0, channels=2),
            AudioStreamInfo(stream_index=1, audio_index=1, channels=1),
        ],
    )
    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(on_output=write_silence_wav, calls=calls))

    result = import_audio_file(source, sessions, ffmpeg="ffmpeg")

    assert (result / "audio" / "audio_import.wav").is_file()
    assert (result / "audio" / "audio_import-ch2.wav").is_file()
    assert (result / "audio" / "audio_import-2.wav").is_file()
    assert len(calls) == 3
    assert [call[call.index("-map") + 1] for call in calls] == ["0:a:0", "0:a:0", "0:a:1"]
    assert calls[0][calls[0].index("-af") + 1] == "pan=mono|c0=c0"
    assert calls[1][calls[1].index("-af") + 1] == "pan=mono|c0=c1"
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["captured_tracks"] == ["audio_import", "audio_import-ch2", "audio_import-2"]
    assert [item["filename"] for item in metadata["audio_sources"]] == ["audio_import.wav", "audio_import-ch2.wav", "audio_import-2.wav"]
    assert metadata["audio_import_channel_mode"] == "split"


def test_import_audio_fails_explicitly_when_ffprobe_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from seance.providers import media_tools

    source = tmp_path / "multitrack.mkv"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"test executable placeholder")
    monkeypatch.setattr(
        "seance.media.audio_import.ensure_media_toolchain_ready",
        media_tools.ensure_media_toolchain_ready,
    )
    monkeypatch.setattr("seance.providers.media_tools.resolve_ffprobe", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="ffprobe introuvable"):
        import_audio_file(source, sessions, ffmpeg=str(ffmpeg))
    assert not sessions.exists()


def test_import_audio_forwards_configured_ffprobe_to_the_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "multitrack.mkv"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"
    captured: list[tuple[str, str]] = []

    def fake_probe(self, _source: str) -> list[AudioStreamInfo]:
        captured.append((str(self.options.get("ffmpeg")), str(self.options.get("ffprobe"))))
        return [AudioStreamInfo(stream_index=0, audio_index=0, channels=1)]

    monkeypatch.setattr("seance.providers.media_tools.FFmpegMediaToolchain.probe_audio_streams", fake_probe)
    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", make_fake_popen(on_output=write_silence_wav))

    result = import_audio_file(source, sessions, ffmpeg="ffmpeg", ffprobe="ffprobe-custom")

    assert (result / "audio" / "audio_import.wav").is_file()
    assert captured == [("ffmpeg", "ffprobe-custom")]


def _write_interleaved_pcm16(path: Path, left: int, right: int, samples: int = 1600) -> None:
    interleaved = np.empty(samples * 2, dtype="<i2")
    interleaved[0::2] = left
    interleaved[1::2] = right
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(interleaved.tobytes())


def _wav_samples(path: Path) -> tuple[int, int, np.ndarray]:
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        rate = stream.getframerate()
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
    return channels, rate, data


def test_import_audio_with_native_provider_splits_stereo_pcm16_without_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "stereo.wav"
    _write_interleaved_pcm16(source, left=1000, right=3000)
    sessions = tmp_path / "sessions"

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the native media provider must not launch FFmpeg")

    monkeypatch.setattr("seance.providers.media_tools.subprocess.Popen", forbidden)
    monkeypatch.setattr("seance.providers.media_tools.subprocess.run", forbidden)

    result = import_audio_file(source, sessions, media_provider="native")

    first = result / "audio" / "audio_import.wav"
    second = result / "audio" / "audio_import-ch2.wav"
    assert first.is_file() and second.is_file()
    channels, rate, first_samples = _wav_samples(first)
    assert (channels, rate) == (1, 16000)
    assert set(first_samples.tolist()) == {1000}
    _, _, second_samples = _wav_samples(second)
    assert set(second_samples.tolist()) == {3000}

    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["captured_tracks"] == ["audio_import", "audio_import-ch2"]
    assert metadata["audio_sources"] == [
        {
            "filename": "audio_import.wav",
            "name": "Audio importé · Canal 1",
            "kind": "import",
            "stream_index": 0,
            "audio_index": 0,
            "source_channel": 1,
            "channels_in_source": 2,
            "normalization": metadata["audio_sources"][0]["normalization"],
        },
        {
            "filename": "audio_import-ch2.wav",
            "name": "Audio importé · Canal 2",
            "kind": "import",
            "stream_index": 0,
            "audio_index": 0,
            "source_channel": 2,
            "channels_in_source": 2,
            "normalization": metadata["audio_sources"][1]["normalization"],
        },
    ]
