from __future__ import annotations

import json
import wave
from pathlib import Path
from unittest.mock import Mock

import pytest

from seance.audio_import import import_audio_file


def test_import_audio_converts_to_durable_session_and_writes_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "Point équipe.mp4"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"\x00\x00" * 100)
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("seance.audio_import.subprocess.run", fake_run)
    monkeypatch.setattr("seance.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
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
    monkeypatch.setattr("seance.audio_import.subprocess.run", lambda *args, **kwargs: Mock(returncode=1, stdout="", stderr="decode failed"))
    monkeypatch.setattr("seance.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")

    with pytest.raises(RuntimeError, match="decode failed"):
        import_audio_file(source, sessions, ffmpeg="ffmpeg")
    assert list(sessions.iterdir()) == []


def test_import_audio_applies_shared_peak_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    source = tmp_path / "quiet-audio.mp3"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(np.full(1600, 1000, dtype="<i2").tobytes())
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("seance.audio_import.subprocess.run", fake_run)
    monkeypatch.setattr("seance.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
    result = import_audio_file(source, sessions, ffmpeg="ffmpeg", normalize=True, max_gain_db=30)

    from seance.audio import _wav_pcm16_stats
    stats = _wav_pcm16_stats(result / "audio" / "audio_import.wav")
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["audio_import_normalization"]["status"] == "normalized"
    assert stats["peak_dbfs"] == pytest.approx(-6.0, abs=0.1)


def test_import_audio_respects_disabled_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np

    source = tmp_path / "quiet-audio.mp3"
    source.write_bytes(b"fake media")
    sessions = tmp_path / "sessions"

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(np.full(1600, 1000, dtype="<i2").tobytes())
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("seance.audio_import.subprocess.run", fake_run)
    monkeypatch.setattr("seance.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")
    result = import_audio_file(source, sessions, ffmpeg="ffmpeg", normalize=False, max_gain_db=30)

    from seance.audio import _wav_pcm16_stats
    stats = _wav_pcm16_stats(result / "audio" / "audio_import.wav")
    metadata = json.loads((result / "metadata" / "seance.json").read_text(encoding="utf-8"))
    assert metadata["audio_import_normalization"]["status"] == "disabled"
    assert stats["peak_dbfs"] == pytest.approx(-30.3, abs=0.2)
