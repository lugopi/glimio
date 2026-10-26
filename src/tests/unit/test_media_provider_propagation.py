from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from seance.processing import minutes, pipeline, transcription
from seance.layout import ensure_session_layout


def test_transcribe_folder_forwards_media_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr("seance.processing.pipeline.transcribe", lambda args: captured.update(vars(args)))
    source = argparse.Namespace(
        directory=str(tmp_path), media_provider="native", provider_options={"native": {}},
    )

    pipeline.transcribe_folder(tmp_path, source)

    assert captured["media_provider"] == "native"


def test_minutes_folder_forwards_media_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr("seance.processing.pipeline.summarize", lambda args: captured.update(vars(args)))
    source = argparse.Namespace(
        directory=str(tmp_path), media_provider="native", provider_options={"native": {}},
    )

    pipeline.minutes_folder(tmp_path, source)

    assert captured["media_provider"] == "native"


def test_minutes_ensure_transcript_forwards_media_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "session"
    layout = ensure_session_layout(folder)
    (layout["audio"] / "micro.wav").write_bytes(b"placeholder")
    captured: dict[str, object] = {}

    def fake_transcribe(args) -> None:
        captured.update(vars(args))
        (layout["transcript"] / "transcription.md").write_text("# ok\n", encoding="utf-8")

    monkeypatch.setattr("seance.processing.minutes.transcribe_audio", fake_transcribe)
    args = argparse.Namespace(
        directory=str(tmp_path), media_provider="native", provider_options={"native": {}},
    )

    minutes._ensure_transcript(folder, args)

    assert captured["media_provider"] == "native"


def test_transcription_imports_with_the_selected_media_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "recording.wav"
    source.write_bytes(b"placeholder")
    captured: dict[str, object] = {}

    def fake_create(provider_id, options=None):
        captured["provider"] = (provider_id, dict(options or {}))
        return object()

    def fake_import(*_args, **kwargs):
        captured["import"] = kwargs
        raise SystemExit("stop")

    monkeypatch.setattr(transcription, "create_media_provider", fake_create)
    monkeypatch.setattr(transcription, "import_audio_file", fake_import)
    args = argparse.Namespace(
        whisper_cli="whisper-cli", model="model.bin", folder=str(source),
        directory=str(tmp_path), provider_options={"native": {"mode": "fast"}},
        media_provider="native", ffmpeg="ffmpeg", ffprobe="ffprobe",
    )

    with pytest.raises(SystemExit, match="stop"):
        transcription.transcribe(args)

    assert captured["provider"] == ("native", {"mode": "fast"})
    assert captured["import"]["media_provider"] == "native"
    assert captured["import"]["media_options"] == {"mode": "fast"}
