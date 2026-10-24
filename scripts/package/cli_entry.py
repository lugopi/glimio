"""PyInstaller entry point for the bundled CLI; source development is unchanged."""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import sys


def _configure_data_root() -> None:
    if not getattr(sys, "frozen", False):
        return
    if os.name == "nt":
        data_root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        data_root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    os.environ.setdefault("GLIMIO_PROJECT_ROOT", str(data_root / "Glimio" / "Data"))


_configure_data_root()


if __name__ == "__main__":
    # Keep the spawned diarization child lean: freeze_support must run before
    # importing the CLI application, otherwise every child loads it too.
    mp.freeze_support()
    from seance.cli import main  # noqa: E402

    main()
