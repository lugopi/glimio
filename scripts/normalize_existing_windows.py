from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from seance.audio import _normalize_wav_peak


def find_tracks(target: Path) -> list[Path]:
    target = target.expanduser().resolve()
    if target.is_file():
        if target.name.casefold() != "windows.wav":
            raise SystemExit("Pass a windows.wav file, a session folder, or the seances/ root.")
        return [target]
    if not target.is_dir():
        raise SystemExit(f"Path not found: {target}")

    direct = target / "audio" / "windows.wav"
    if direct.is_file():
        return [direct]
    tracks = sorted(path for path in target.rglob("windows.wav") if path.is_file() and path.parent.name.casefold() == "audio")
    if not tracks:
        raise SystemExit(f"No audio/windows.wav tracks found under {target}")
    return tracks


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Raise quiet Windows loopback WAVs toward -6 dBFS without clipping. "
            "The original is backed up once as windows.original.wav by default."
        )
    )
    parser.add_argument("path", help="windows.wav, one session folder, or the seances/ root")
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Modify windows.wav without first creating windows.original.wav",
    )
    args = parser.parse_args()

    for track in find_tracks(Path(args.path)):
        backup = track.with_name("windows.original.wav")
        if not args.no_backup and not backup.exists():
            shutil.copy2(track, backup)
        try:
            result = _normalize_wav_peak(track, enabled=True)
        except Exception as exc:
            print(f"{track}: normalization failed; original WAV was kept: {exc}")
            continue
        print(
            f"{track}: status={result['status']}, "
            f"gain=+{result['gain_applied_db']:.1f} dB, "
            f"peak={result.get('peak_before_dbfs')} -> {result.get('peak_after_dbfs')} dBFS, "
            f"RMS={result.get('rms_before_dbfs')} -> {result.get('rms_after_dbfs')} dBFS"
        )


if __name__ == "__main__":
    main()
