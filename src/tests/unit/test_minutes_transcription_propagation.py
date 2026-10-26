from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from seance.processing import minutes


def _prepare_session(tmp_path: Path) -> Path:
    folder = tmp_path / "session"
    (folder / "audio").mkdir(parents=True)
    (folder / "audio" / "micro.wav").write_bytes(b"audio")
    return folder


def _patch_transcription(monkeypatch: pytest.MonkeyPatch, captured: dict[str, argparse.Namespace]) -> None:
    monkeypatch.setattr(minutes, "has_audio", lambda _folder: True)
    monkeypatch.setattr(
        minutes, "get_transcript_path",
        lambda folder, name="transcription.md": Path(folder) / "transcript" / name,
    )

    def fake_transcribe(args: argparse.Namespace) -> None:
        captured["args"] = args
        transcript = Path(args.folder) / "transcript" / "transcription.md"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text("texte", encoding="utf-8")

    monkeypatch.setattr(minutes, "transcribe_audio", fake_transcribe)


def test_ensure_transcript_keeps_the_configured_audio_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _prepare_session(tmp_path)
    captured: dict[str, argparse.Namespace] = {}
    _patch_transcription(monkeypatch, captured)
    args = argparse.Namespace(
        folder=str(folder),
        ffmpeg="C:/tools/ffmpeg.exe",
        ffprobe="C:/tools/ffprobe.exe",
        audio_enhancement_provider="no-enhancement",
        source_separation_provider="no-separation",
        speaker_embedding_provider="speechbrain-ecapa",
    )

    minutes._ensure_transcript(folder, args)

    transcription_args = captured["args"]
    assert transcription_args.ffmpeg == "C:/tools/ffmpeg.exe"
    assert transcription_args.ffprobe == "C:/tools/ffprobe.exe"
    assert transcription_args.audio_enhancement_provider == "no-enhancement"
    assert transcription_args.source_separation_provider == "no-separation"
    assert transcription_args.speaker_embedding_provider == "speechbrain-ecapa"


def test_ensure_transcript_does_not_default_to_ffmpeg_denoise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _prepare_session(tmp_path)
    captured: dict[str, argparse.Namespace] = {}
    _patch_transcription(monkeypatch, captured)

    minutes._ensure_transcript(folder, argparse.Namespace(folder=str(folder)))

    assert captured["args"].audio_enhancement_provider == "no-enhancement"
    assert captured["args"].ffprobe == "ffprobe"
