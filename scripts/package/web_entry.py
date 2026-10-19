"""PyInstaller entry point for the bundled Web app; source development is unchanged."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def _configure_runtime() -> None:
    if not getattr(sys, "frozen", False):
        return
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    os.environ.setdefault("GLIMIO_PROJECT_ROOT", str(local_app_data / "Glimio" / "Data"))
    os.environ.setdefault("GLIMIO_ANGULAR_DIST_DIR", str(Path(sys._MEIPASS) / "angular"))


_configure_runtime()

from web.app import main  # noqa: E402


if __name__ == "__main__":
    if sys.argv[1:] == ["--check-bundle"]:
        from web.app import ANGULAR_DIST_DIR

        index_file = ANGULAR_DIST_DIR / "index.html"
        if not index_file.is_file():
            raise SystemExit(f"Frontend Glimio empaqueté introuvable : {index_file}")
        print(f"Frontend Glimio inclus : {index_file}")
        raise SystemExit(0)
    main()
