"""On-demand Python provider runtime for frozen Glimio releases.

The base CLI/Web bundle stays small. Heavy optional wheels are installed into a
separate user-managed CPython site-packages directory only after the user asks
for a provider. The runtime archive is pinned and SHA-256 verified before use.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import site
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.request import Request, urlopen

PYTHON_RUNTIME_VERSION = "3.12.15"
PYTHON_RUNTIME_BUILD = "20261001"
_RUNTIME_RELEASE_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYTHON_RUNTIME_BUILD}/"
)
# Hashes are published by the upstream python-build-standalone release page.
# Keep targets limited to the two platforms for which Glimio ships binaries.
_RUNTIME_ASSETS = {
    "win32": {
        "asset": f"cpython-{PYTHON_RUNTIME_VERSION}+{PYTHON_RUNTIME_BUILD}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
        "sha256": "52124cee54126f3f360eaa378288f6f64c402c983a3c14c95eff67f4af986aaa",
    },
    "linux": {
        "asset": f"cpython-{PYTHON_RUNTIME_VERSION}+{PYTHON_RUNTIME_BUILD}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "sha256": "7bb1659e3235077b7f63d5b6eb6ce653c6fcd6c5041e9d5f73b42ce10421464d",
    },
}
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 500 * 1024 * 1024
ProgressCallback = Callable[[str], None]


def _machine() -> str:
    return platform.machine().casefold().replace(" ", "")


def supports_managed_provider_runtime() -> bool:
    """Whether this platform has a pinned extension-runtime build."""
    return sys.platform in _RUNTIME_ASSETS and _machine() in {"x86_64", "amd64"}


def provider_runtime_root(project_root: str | Path) -> Path:
    """Return the user-data path holding the optional Python runtime and wheels."""
    return Path(project_root).expanduser().resolve() / "provider-runtime"


def _runtime_executable(runtime_root: Path) -> Path:
    python_root = runtime_root / "python"
    if sys.platform == "win32":
        return python_root / "python.exe"
    return python_root / "bin" / "python3.12"


def _safe_extract_runtime(archive_path: Path, destination: Path) -> None:
    """Extract a trusted, checksummed tar archive without allowing path escapes."""
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        total_size = sum(max(0, member.size) for member in members)
        if total_size > MAX_UNPACKED_BYTES:
            raise RuntimeError("L’archive Python dépasse la taille décompressée autorisée.")
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise RuntimeError("L’archive Python contient un chemin non sûr.")
            target = (destination / Path(*name.parts)).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise RuntimeError("L’archive Python tente d’écrire en dehors du dossier temporaire.")
            if member.isdev() or member.isfifo():
                raise RuntimeError("L’archive Python contient un type de fichier interdit.")
            if member.issym():
                link_name = PurePosixPath(member.linkname)
                if link_name.is_absolute():
                    raise RuntimeError("L’archive Python contient un lien symbolique absolu.")
                link_target = (target.parent / Path(*link_name.parts)).resolve()
                if link_target != destination_resolved and destination_resolved not in link_target.parents:
                    raise RuntimeError("L’archive Python contient un lien symbolique non sûr.")
            if member.islnk():
                link_name = PurePosixPath(member.linkname)
                if link_name.is_absolute() or ".." in link_name.parts:
                    raise RuntimeError("L’archive Python contient un lien physique non sûr.")
        # All entries have been checked before extracting the archive.
        archive.extractall(destination)


def _site_packages_for_python(python: Path, runtime_root: Path) -> Path:
    result = subprocess.run(
        [str(python), "-c", "import json,sysconfig; print(json.dumps(sysconfig.get_paths()['purelib']))"],
        capture_output=True, text=True, check=True, timeout=20,
    )
    value = json.loads(result.stdout.strip())
    site_packages = Path(value).resolve()
    root_resolved = runtime_root.resolve()
    if site_packages != root_resolved and root_resolved not in site_packages.parents:
        raise RuntimeError("Le runtime Python a retourné un chemin site-packages hors de son dossier.")
    return site_packages


def _ensure_runtime_pip(python: Path, *, on_progress: ProgressCallback | None = None) -> None:
    """Ensure the standalone interpreter can install wheels without system Python."""
    try:
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            capture_output=True, text=True, check=True, timeout=20,
        )
        return
    except (OSError, subprocess.SubprocessError):
        pass

    if on_progress:
        on_progress("Préparation de pip dans le runtime Python isolé…\n")
    try:
        subprocess.run(
            [str(python), "-m", "ensurepip", "--upgrade"],
            capture_output=True, text=True, check=True, timeout=60,
        )
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            capture_output=True, text=True, check=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Le runtime Python téléchargé ne fournit pas pip et n’a pas pu le préparer via ensurepip."
        ) from exc


def _read_runtime_metadata(runtime_root: Path) -> dict[str, object] | None:
    path = runtime_root / "runtime.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    asset = _RUNTIME_ASSETS.get(sys.platform)
    if (
        not isinstance(payload, dict)
        or payload.get("python_version") != PYTHON_RUNTIME_VERSION
        or payload.get("standalone_build") != PYTHON_RUNTIME_BUILD
        or asset is None
        or payload.get("archive_sha256") != asset["sha256"]
    ):
        return None
    for key in ("python_executable", "site_packages"):
        value = payload.get(key)
        if not isinstance(value, str):
            return None
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        target = (runtime_root / Path(*relative.parts)).resolve()
        root_resolved = runtime_root.resolve()
        if target != root_resolved and root_resolved not in target.parents:
            return None
    return payload


def _write_runtime_metadata(runtime_root: Path, *, python: Path, site_packages: Path, sha256: str) -> None:
    relative_python = python.resolve().relative_to(runtime_root.resolve()).as_posix()
    relative_site = site_packages.resolve().relative_to(runtime_root.resolve()).as_posix()
    payload: dict[str, object] = {
        "python_version": PYTHON_RUNTIME_VERSION,
        "standalone_build": PYTHON_RUNTIME_BUILD,
        "archive_sha256": sha256,
        "python_executable": relative_python,
        "site_packages": relative_site,
        "dll_directories": [],
    }
    metadata_path = runtime_root / "runtime.json"
    temporary_path = runtime_root / "runtime.json.tmp"
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, metadata_path)


def ensure_managed_python(
    project_root: str | Path,
    *,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Download, verify and extract the on-demand CPython runtime if missing."""
    if not supports_managed_provider_runtime():
        raise RuntimeError(
            "L’installation des providers Python précompilés est actuellement disponible sur Windows x64 et Linux x86_64."
        )

    runtime_root = provider_runtime_root(project_root)
    python = _runtime_executable(runtime_root)
    metadata = _read_runtime_metadata(runtime_root)
    if metadata and python.is_file():
        try:
            result = subprocess.run(
                [str(python), "-c", "import platform; print(platform.python_version())"],
                capture_output=True, text=True, check=True, timeout=20,
            )
            if result.stdout.strip() == PYTHON_RUNTIME_VERSION:
                _ensure_runtime_pip(python, on_progress=on_progress)
                return python
        except (OSError, subprocess.SubprocessError):
            pass

    if on_progress:
        on_progress(f"Téléchargement du runtime Python {PYTHON_RUNTIME_VERSION}…\n")
    asset = _RUNTIME_ASSETS[sys.platform]
    url = _RUNTIME_RELEASE_URL + asset["asset"]
    runtime_root.parent.mkdir(parents=True, exist_ok=True)
    download_path: Path | None = None
    stage: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="glimio-python-runtime-", suffix=".tar.gz", dir=runtime_root.parent, delete=False,
        ) as stream:
            download_path = Path(stream.name)
            digest = hashlib.sha256()
            received = 0
            request = Request(url, headers={"User-Agent": "Glimio-provider-installer/0.5.0"})
            with urlopen(request, timeout=45) as response:
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_ARCHIVE_BYTES:
                    raise RuntimeError("L’archive Python dépasse la taille de téléchargement autorisée.")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_ARCHIVE_BYTES:
                        raise RuntimeError("L’archive Python dépasse la taille de téléchargement autorisée.")
                    stream.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != asset["sha256"]:
            raise RuntimeError("La vérification SHA-256 du runtime Python a échoué ; aucun fichier n’a été installé.")
        if on_progress:
            on_progress(f"Archive Python vérifiée ({received / (1024 * 1024):.1f} MiB). Extraction…\n")

        stage = Path(tempfile.mkdtemp(prefix="glimio-python-stage-", dir=runtime_root.parent))
        _safe_extract_runtime(download_path, stage)
        staged_python = _runtime_executable(stage)
        if not staged_python.is_file():
            raise RuntimeError("L’archive Python vérifiée ne contient pas l’interpréteur attendu.")
        # Verify sysconfig resolves site-packages inside the extracted runtime.
        _site_packages_for_python(staged_python, stage)

        # Replacing the managed runtime is safe because a valid runtime would
        # have returned above and its site-packages may contain installed providers.
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
        runtime_root.mkdir(parents=True, exist_ok=True)
        staged_python_root = stage / "python"
        os.replace(staged_python_root, runtime_root / "python")
        python = _runtime_executable(runtime_root)
        site_packages = _site_packages_for_python(python, runtime_root)
        site_packages.mkdir(parents=True, exist_ok=True)
        _ensure_runtime_pip(python, on_progress=on_progress)
        _write_runtime_metadata(runtime_root, python=python, site_packages=site_packages, sha256=str(asset["sha256"]))
        if on_progress:
            on_progress("Runtime Python installé. Installation des dépendances provider…\n")
        return python
    finally:
        if download_path is not None:
            download_path.unlink(missing_ok=True)
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def refresh_managed_provider_metadata(project_root: str | Path) -> None:
    """Record import and DLL search paths after installing provider wheels."""
    runtime_root = provider_runtime_root(project_root)
    metadata = _read_runtime_metadata(runtime_root)
    python = _runtime_executable(runtime_root)
    if metadata is None or not python.is_file():
        raise RuntimeError("Le runtime Python des providers n’est pas installé correctement.")
    site_value = metadata.get("site_packages")
    if not isinstance(site_value, str):
        site_packages = _site_packages_for_python(python, runtime_root)
    else:
        site_packages = (runtime_root / site_value).resolve()
    if site_packages != runtime_root.resolve() and runtime_root.resolve() not in site_packages.parents:
        raise RuntimeError("Chemin site-packages invalide dans les métadonnées du runtime provider.")
    site_packages.mkdir(parents=True, exist_ok=True)

    dll_directories: list[str] = []
    if sys.platform == "win32":
        python_root = runtime_root / "python"
        candidates = {python_root.resolve(), site_packages.resolve()}
        # Precompute the folders containing native wheels' DLLs once at install
        # time. Startup only restores these handles instead of rescanning torch.
        for dll in site_packages.rglob("*.dll"):
            candidates.add(dll.parent.resolve())
        dll_directories = sorted(path.relative_to(runtime_root.resolve()).as_posix() for path in candidates if path.is_dir())

    metadata["dll_directories"] = dll_directories
    temporary_path = runtime_root / "runtime.json.tmp"
    temporary_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, runtime_root / "runtime.json")


def record_installed_provider(project_root: str | Path, provider_id: str, packages: tuple[str, ...]) -> None:
    runtime_root = provider_runtime_root(project_root)
    path = runtime_root / "installed-providers.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        payload = {}
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, dict):
        providers = {}
    from datetime import datetime

    providers[provider_id] = {"packages": list(packages), "installed_at": datetime.now().astimezone().isoformat()}
    content = {"python_version": PYTHON_RUNTIME_VERSION, "providers": providers}
    temporary_path = runtime_root / "installed-providers.json.tmp"
    temporary_path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)


_DLL_DIRECTORY_HANDLES: list[object] = []


def activate_managed_provider_runtime() -> None:
    """Make installed extension packages importable in a frozen Glimio process."""
    if not getattr(sys, "frozen", False):
        return
    data_root = os.environ.get("GLIMIO_PROJECT_ROOT")
    if not data_root:
        return
    runtime_root = provider_runtime_root(data_root)
    metadata = _read_runtime_metadata(runtime_root)
    if metadata is None:
        return
    site_value = metadata.get("site_packages")
    if isinstance(site_value, str):
        site_path = (runtime_root / site_value).resolve()
        if site_path.is_dir() and (site_path == runtime_root.resolve() or runtime_root.resolve() in site_path.parents):
            site.addsitedir(str(site_path))
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        raw_directories = metadata.get("dll_directories", [])
        if not isinstance(raw_directories, list):
            return
        for relative in raw_directories:
            if not isinstance(relative, str):
                continue
            directory = (runtime_root / relative).resolve()
            if directory.is_dir() and (directory == runtime_root.resolve() or runtime_root.resolve() in directory.parents):
                try:
                    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
                except OSError:
                    continue
