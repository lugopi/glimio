"""SRT decoding helpers used inside command-line transcription adapters."""
from __future__ import annotations

import re
from pathlib import Path

from ..common import log


def srt_seconds(stamp: str) -> float:
    stamp = stamp.strip().replace(".", ",")
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2}),(\d{1,3})", stamp)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {stamp!r}")
    hours, minutes, seconds, milliseconds = match.groups()
    milliseconds = milliseconds.ljust(3, "0")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def read_srt(path: str | Path) -> list[tuple[float, float, str]]:
    """Decode whisper.cpp SRT output into vendor-independent timed text."""
    source = Path(path)
    if not source.is_file():
        raise SystemExit(f"SRT file not found: {source}")
    raw = source.read_bytes()
    if not raw:
        return []
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = None
        for encoding in ("utf-8", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("latin-1")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    segments: list[tuple[float, float, str]] = []
    for block in re.split(r"\n[ \t]*\n+", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = re.fullmatch(
            r"\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
            r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})(?:\s+.*)?",
            lines[timing_index],
        )
        if not match:
            log(f"Ignoring invalid timestamp: {lines[timing_index]!r}", error=True)
            continue
        try:
            start, end = srt_seconds(match.group(1)), srt_seconds(match.group(2))
        except ValueError as exc:
            log(str(exc), error=True)
            continue
        if end < start:
            log("Ignoring segment: end is before start.", error=True)
            continue
        content = " ".join(lines[timing_index + 1:]).strip()
        if content:
            segments.append((start, end, content))
    return segments
