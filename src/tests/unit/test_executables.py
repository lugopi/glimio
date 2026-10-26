from __future__ import annotations

from pathlib import Path

import pytest

from seance import executables
from seance.executables import resolve_command, resolve_ffprobe


def test_resolve_command_accepts_an_existing_explicit_path(tmp_path: Path) -> None:
    executable = tmp_path / "bin" / "ffmpeg.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"binary")

    assert resolve_command(str(executable), default="ffmpeg") == str(executable.resolve())


def test_resolve_command_rejects_a_missing_explicit_path(tmp_path: Path) -> None:
    missing = tmp_path / "bin" / "ffmpeg.exe"

    assert resolve_command(str(missing), default="ffmpeg") is None


def test_resolve_command_finds_a_bare_name_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_which(name: str) -> str | None:
        calls.append(name)
        return "/opt/tools/custom-ffmpeg" if name == "custom-ffmpeg" else None

    monkeypatch.setattr(executables.shutil, "which", fake_which)

    assert resolve_command("custom-ffmpeg", default="ffmpeg") == "/opt/tools/custom-ffmpeg"
    assert calls == ["custom-ffmpeg"]


def test_resolve_command_uses_the_default_for_empty_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executables.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert resolve_command(None, default="ffmpeg") == "/usr/bin/ffmpeg"
    assert resolve_command("   ", default="ffmpeg") == "/usr/bin/ffmpeg"


def test_resolve_command_never_falls_back_from_a_custom_bare_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_which(name: str) -> str | None:
        calls.append(name)
        return None

    monkeypatch.setattr(executables.shutil, "which", fake_which)

    assert resolve_command("my-ffmpeg", default="ffmpeg") is None
    assert calls == ["my-ffmpeg"]


def test_resolve_ffprobe_prefers_the_sibling_of_ffmpeg_over_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"binary")
    ffprobe.write_bytes(b"binary")
    monkeypatch.setattr(executables.shutil, "which", lambda name: "/path/ffprobe" if name in {"ffprobe", "ffprobe.exe"} else None)

    assert resolve_ffprobe(str(ffmpeg)) == str(ffprobe)


def test_resolve_ffprobe_default_falls_back_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_bytes(b"binary")
    monkeypatch.setattr(
        executables.shutil, "which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    assert resolve_ffprobe(str(ffmpeg)) == "/usr/bin/ffprobe"


def test_resolve_ffprobe_explicit_bare_name_does_not_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"binary")
    (tmp_path / "ffprobe.exe").write_bytes(b"binary")
    monkeypatch.setattr(executables.shutil, "which", lambda _name: None)

    assert resolve_ffprobe(str(ffmpeg), "my-ffprobe") is None


def test_resolve_ffprobe_explicit_missing_path_does_not_fall_back_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"binary")
    monkeypatch.setattr(executables.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    missing = tmp_path / "tools" / "ffprobe.exe"

    assert resolve_ffprobe(str(ffmpeg), str(missing)) is None
