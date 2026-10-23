"""PyInstaller entry point for the bundled CLI; source development is unchanged."""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import sys


def _configure_data_root() -> None:
    if not getattr(sys, "frozen", False):
        return
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    os.environ.setdefault("GLIMIO_PROJECT_ROOT", str(local_app_data / "Glimio" / "Data"))


_configure_data_root()


if __name__ == "__main__":
    # Keep the spawned diarization child lean: freeze_support must run before
    # importing the CLI application, otherwise every child loads it too.
    mp.freeze_support()
    from seance.cli import main  # noqa: E402

    main()
