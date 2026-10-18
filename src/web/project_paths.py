from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Iterable


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path.expanduser().absolute()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def _ancestors(start: Path) -> list[Path]:
    resolved = start.expanduser().resolve()
    return [resolved, *resolved.parents]


def _looks_like_seance_root(path: Path) -> bool:
    """Recognize this repository in both flat and ``src/`` package layouts."""
    has_project_file = (path / "pyproject.toml").is_file()
    has_session_folder = (path / "seances").is_dir()
    has_source_package = (path / "src" / "seance").is_dir() or (path / "seance").is_dir()
    return has_project_file and (has_session_folder or has_source_package)


def discover_project_root(
    *,
    start_dir: str | Path | None = None,
    package_file: str | Path | None = None,
    explicit_root: str | Path | None = None,
) -> Path:
    """Find the project root regardless of whether Web is launched from root or src/.

    ``GLIMIO_PROJECT_ROOT`` (or legacy ``SEANCE_PROJECT_ROOT``; passed as ``explicit_root``) has highest priority. In
    editable installs, paths next to ``src/web/app.py`` identify the real repository;
    the current working directory is a fallback for ordinary installed packages.
    """
    override = explicit_root if explicit_root is not None else (
        os.environ.get("GLIMIO_PROJECT_ROOT") or os.environ.get("SEANCE_PROJECT_ROOT")
    )
    if override is not None and str(override).strip():
        return Path(override).expanduser().resolve()

    cwd = Path(start_dir).expanduser() if start_dir is not None else Path.cwd()
    cwd = cwd.resolve()
    source_file = Path(package_file).expanduser().resolve() if package_file else Path(__file__).resolve()

    # Prefer the source package's ancestors: editable installs point here even if the
    # command was launched from another working directory.
    candidates = _unique_paths([*_ancestors(source_file.parent), *_ancestors(cwd)])
    for candidate in candidates:
        if _looks_like_seance_root(candidate):
            return candidate

    # During initial setup, seances/ may not exist yet; still recognize the project.
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (
            (candidate / "src" / "seance").is_dir() or (candidate / "seance").is_dir()
        ):
            return candidate

    return cwd


def resolve_session_root(
    project_root: str | Path,
    directory: str | Path | None = None,
) -> Path:
    """Resolve the sessions directory relative to the detected project root."""
    root = Path(project_root).expanduser().resolve()
    raw = directory
    if raw is None:
        raw = os.environ.get("GLIMIO_DIRECTORY") or os.environ.get("SEANCE_DIRECTORY")
    if raw is None or not str(raw).strip():
        return (root / "seances").resolve()

    requested = Path(raw).expanduser()
    if requested.is_absolute():
        return requested.resolve()
    return (root / requested).resolve()
