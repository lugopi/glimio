"""Resolve external media executables without launching them."""
from __future__ import annotations

import shutil
from pathlib import Path


def resolve_command(command: str | None, *, default: str) -> str | None:
    """Resolve a bare command on PATH or an explicit file path; None when missing.

    An empty value falls back to ``default``. An explicit path (containing a path
    separator) must exist; a bare name is looked up on PATH only, so a custom
    command never silently falls back to the default executable.
    """
    text = str(command or "").strip()
    if not text:
        text = default
    text = str(Path(text).expanduser())
    if "/" in text or "\\" in text:
        path = Path(text)
        return str(path.resolve()) if path.is_file() else None
    return shutil.which(text) or None


def resolve_ffprobe(ffmpeg: str | None, ffprobe: str | None = None) -> str | None:
    """Resolve ffprobe: explicit setting, then beside FFmpeg, then on PATH.

    An explicit ``ffprobe`` value is authoritative: when it points to a missing
    file the function returns None instead of silently probing another ffprobe,
    because a mismatched probe can misreport or drop audio streams.
    """
    requested = str(ffprobe or "").strip()
    if requested and requested.casefold() not in {"ffprobe", "ffprobe.exe"}:
        if "/" in requested or "\\" in requested:
            return resolve_command(requested, default=requested)
        return shutil.which(requested) or None

    resolved_ffmpeg = resolve_command(ffmpeg, default="ffmpeg")
    if resolved_ffmpeg:
        ffmpeg_path = Path(resolved_ffmpeg)
        names = ("ffprobe.exe", "ffprobe") if ffmpeg_path.suffix.casefold() == ".exe" else ("ffprobe", "ffprobe.exe")
        for name in names:
            sibling = ffmpeg_path.parent / name
            if sibling.is_file():
                return str(sibling)
    return shutil.which("ffprobe") or shutil.which("ffprobe.exe") or None
