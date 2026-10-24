from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from seance.media.audio_import import _audio_streams as _real_audio_streams, import_audio_file


@pytest.fixture(autouse=True)
def _default_probe_reports_one_audio_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    # Individual import tests focus on conversion/normalization, not ffprobe itself.
    monkeypatch.setattr(
        "seance.media.audio_import._audio_streams",
        lambda _source, _ffmpeg: [{"audio_index": 0, "stream_index": 0, "channels": 1}],
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

    monkeypatch.setattr("seance.media.audio_import.subprocess.Popen", make_fake_popen(on_output=write_silence_wav, calls=calls))
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
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
    monkeypatch.setattr("seance.media.audio_import.subprocess.Popen", make_fake_popen(returncode=1, stderr="decode failed"))
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")

    with pytest.raises(RuntimeError, match="decode failed"):
        import_audio_file(source, sessions, ffmpeg="ffmpeg")
    assert list(sessions.iterdir()) == []


def test_import_audio_applies_shared_peak_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "quiet-audio.mp3"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"

    monkeypatch.setattr("seance.media.audio_import.subprocess.Popen", make_fake_popen(on_output=write_quiet_wav))
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
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

    monkeypatch.setattr("seance.media.audio_import.subprocess.Popen", make_fake_popen(on_output=write_quiet_wav))
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
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

    monkeypatch.setattr("seance.media.audio_import.subprocess.Popen", make_fake_popen(on_output=write_quiet_wav))
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
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
        "seance.media.audio_import._audio_streams",
        lambda _source, _ffmpeg: [{"audio_index": 0, "channels": 2}, {"audio_index": 1, "channels": 1}],
    )
    monkeypatch.setattr("seance.media.audio_import.subprocess.Popen", make_fake_popen(on_output=write_silence_wav, calls=calls))
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")

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
    from seance.media import audio_import

    source = tmp_path / "multitrack.mkv"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"
    monkeypatch.setattr("seance.media.audio_import.shutil.which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr("seance.media.audio_import._ffprobe_for", lambda _ffmpeg: None)
    monkeypatch.setattr("seance.media.audio_import._audio_streams", _real_audio_streams)

    with pytest.raises(RuntimeError, match="ffprobe est requis"):
        audio_import.import_audio_file(source, sessions, ffmpeg="ffmpeg")
    assert list(sessions.iterdir()) == []
