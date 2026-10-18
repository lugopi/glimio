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


def test_import_audio_removes_partial_session_when_ffmpeg_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "broken.wav"
    source.write_bytes(b"not a real wav")
    sessions = tmp_path / "sessions"
    monkeypatch.setattr("seance.audio_import.subprocess.run", lambda *args, **kwargs: Mock(returncode=1, stdout="", stderr="decode failed"))
    monkeypatch.setattr("seance.audio_import.shutil.which", lambda _name: "/usr/bin/ffmpeg")

    with pytest.raises(RuntimeError, match="decode failed"):
        import_audio_file(source, sessions, ffmpeg="ffmpeg")
    assert list(sessions.iterdir()) == []
