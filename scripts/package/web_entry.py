"""PyInstaller entry point for the bundled Web app; source development is unchanged."""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import sys


def _configure_runtime() -> None:
    if not getattr(sys, "frozen", False):
        return
    if os.name == "nt":
        data_root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        data_root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    os.environ.setdefault("GLIMIO_PROJECT_ROOT", str(data_root / "Glimio" / "Data"))
    os.environ.setdefault("GLIMIO_ANGULAR_DIST_DIR", str(Path(sys._MEIPASS) / "angular"))


_configure_runtime()


if __name__ == "__main__":
    # Keep the spawned diarization child lean: freeze_support must run before
    # importing the web application, otherwise every child loads FastAPI too.
    mp.freeze_support()
    if sys.argv[1:] == ["--check-bundle"]:
        from web.app import ANGULAR_DIST_DIR

        index_file = ANGULAR_DIST_DIR / "index.html"
        if not index_file.is_file():
            raise SystemExit(f"Frontend Glimio empaqueté introuvable : {index_file}")
        print(f"Frontend Glimio inclus : {index_file}")
        raise SystemExit(0)
    from web.app import main  # noqa: E402

    main()
