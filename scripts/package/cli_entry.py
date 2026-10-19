"""PyInstaller entry point for the bundled CLI; source development is unchanged."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def _configure_data_root() -> None:
    if not getattr(sys, "frozen", False):
        return
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    os.environ.setdefault("GLIMIO_PROJECT_ROOT", str(local_app_data / "Glimio" / "Data"))


_configure_data_root()

from seance.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
