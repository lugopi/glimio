"""Safe on-demand installation of trusted built-in provider dependencies.

Source installs use the active Python environment. Frozen releases download a
small, checksummed CPython runtime only when a Python provider is requested, and
install that provider's allow-listed packages into its site-packages directory.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import importlib
import importlib.util
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Literal

from .contracts import ProviderInfo
from ..provider_runtime import (
    ensure_managed_python,
    record_installed_provider,
    refresh_managed_provider_metadata,
    supports_managed_provider_runtime,
)

InstallState = Literal["queued", "running", "succeeded", "failed"]
_EXTRA_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PACKAGE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:(?:===|==|!=|~=|<=|>=|<|>)[A-Za-z0-9][A-Za-z0-9.!+_-]*)?$"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _cross_process_install_lock(lock_root: Path):
    """Serialize provider package installation across CLI and Web processes."""
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / ".provider-install.lock"
    with lock_path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.2)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def python_install_runtime_available(*, frozen: bool | None = None) -> bool:
    """Whether this build can install the catalogued Python dependencies."""
    is_frozen = bool(getattr(sys, "frozen", False) if frozen is None else frozen)
    if is_frozen:
        return supports_managed_provider_runtime()
    return importlib.util.find_spec("pip") is not None


@dataclass(slots=True)
class _InstallRecord:
    id: str
    provider_id: str
    state: InstallState = "queued"
    message: str = "Installation en attente…"
    output: str = ""
    returncode: int | None = None
    restart_required: bool = True
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "state": self.state,
            "message": self.message,
            "output": self.output[-12000:],
            "returncode": self.returncode,
            "restart_required": self.restart_required,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class ProviderInstallManager:
    """Run one provider installation at a time and expose its progress."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pip_lock = threading.Lock()
        self._records: dict[str, _InstallRecord] = {}

    def start(
        self,
        provider: ProviderInfo,
        *,
        project_root: str | Path,
        frozen: bool | None = None,
    ) -> dict[str, Any]:
        if not (provider.python_install_extra or provider.python_install_packages):
            raise ValueError(f"Le provider {provider.id} ne déclare aucune dépendance Python installable automatiquement.")
        is_frozen = bool(getattr(sys, "frozen", False) if frozen is None else frozen)
        self._validate_provider_metadata(provider)
        if is_frozen and not supports_managed_provider_runtime():
            raise RuntimeError(
                "L’installation des providers Python dans les éditions précompilées est prise en charge sur Windows x64 "
                "et Linux x86_64. Consultez `glimio providers info` pour les autres méthodes d’installation."
            )
        if not is_frozen and importlib.util.find_spec("pip") is None:
            raise RuntimeError("Le module pip n’est pas disponible dans l’environnement Python qui exécute Glimio.")

        with self._lock:
            active = next((item for item in self._records.values() if item.state in {"queued", "running"}), None)
            if active is not None:
                if active.provider_id == provider.id:
                    return active.to_dict()
                raise RuntimeError(
                    f"Une installation Python est déjà en cours pour {active.provider_id}. "
                    "Attendez sa fin avant d’en lancer une autre."
                )
            record = _InstallRecord(
                id=uuid.uuid4().hex,
                provider_id=provider.id,
                restart_required=provider.restart_after_python_install,
            )
            self._records[record.id] = record
            self._prune_locked()

        root = Path(project_root).expanduser().resolve()
        thread = threading.Thread(
            target=self._run,
            args=(record.id, provider, root, is_frozen),
            name=f"glimio-provider-install-{provider.id}",
            daemon=True,
        )
        thread.start()
        return self.get(record.id) or record.to_dict()

    @staticmethod
    def _validate_provider_metadata(provider: ProviderInfo) -> None:
        if provider.python_install_extra and not _EXTRA_PATTERN.fullmatch(provider.python_install_extra):
            raise ValueError("Nom d’extra Python invalide dans les métadonnées du provider.")
        packages = tuple(provider.python_install_packages)
        if any(not item or not _PACKAGE_PATTERN.fullmatch(item) for item in packages):
            raise ValueError("Liste de paquets déclarée invalide. Seuls les spécificateurs de paquets du catalogue sont acceptés.")

    def get(self, install_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._records.get(install_id)
            return item.to_dict() if item is not None else None

    def _prune_locked(self) -> None:
        finished = [item.id for item in self._records.values() if item.state in {"succeeded", "failed"}]
        for install_id in finished[:-30]:
            self._records.pop(install_id, None)

    def _append(self, install_id: str, value: str) -> None:
        with self._lock:
            item = self._records.get(install_id)
            if item is not None:
                item.output = (item.output + value)[-12000:]

    def _update(self, install_id: str, **changes: Any) -> None:
        with self._lock:
            item = self._records.get(install_id)
            if item is not None:
                for key, value in changes.items():
                    setattr(item, key, value)

    @staticmethod
    def _is_glimio_source_tree(root: Path) -> bool:
        project_file = root / "pyproject.toml"
        package_marker = root / "src" / "seance" / "__init__.py"
        if not project_file.is_file() or not package_marker.is_file():
            return False
        try:
            try:
                import tomllib
            except ImportError:  # Python 3.10 source installs may use the dev extra.
                import tomli as tomllib  # type: ignore[no-redef]
            payload = tomllib.loads(project_file.read_text(encoding="utf-8"))
            return payload.get("project", {}).get("name") == "glimio-notes"
        except (OSError, ValueError, AttributeError, ImportError):
            return False

    def _build_command(self, provider: ProviderInfo, root: Path) -> tuple[list[str], Path]:
        """Build an installation command for a non-frozen source environment."""
        pyproject = root / "pyproject.toml"
        if provider.python_install_extra and pyproject.is_file() and self._is_glimio_source_tree(root):
            requirement = f".[{provider.python_install_extra}]"
            return [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-e", requirement], root
        if provider.python_install_packages:
            return [
                sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                *provider.python_install_packages,
            ], root
        raise RuntimeError(
            "Le projet source Glimio pyproject.toml est introuvable et aucun paquet de repli n’est déclaré pour ce provider."
        )

    @staticmethod
    def _build_managed_command(provider: ProviderInfo, python: Path) -> tuple[list[str], Path]:
        """Install into the on-demand runtime, never into PyInstaller's internals."""
        packages = tuple(provider.python_install_packages)
        if not packages:
            raise RuntimeError(
                f"Le provider {provider.id} ne déclare pas de paquets compatibles avec le runtime précompilé."
            )
        command = [
            str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
            *packages,
        ]
        return command, python.parent

    def _run(self, install_id: str, provider: ProviderInfo, root: Path, frozen: bool) -> None:
        self._update(install_id, state="queued", message="En attente du verrou d’installation Python…")
        try:
            with self._pip_lock:
                lock_root = root if frozen else root / ".glimio"
                self._update(install_id, state="queued", message="En attente des autres installations de providers…")
                with _cross_process_install_lock(lock_root):
                    if frozen:
                        self._update(
                            install_id, state="running",
                            message="Préparation du runtime Python provider (première installation uniquement)…",
                            started_at=_now(),
                        )
                        python = ensure_managed_python(
                            root, on_progress=lambda chunk: self._append(install_id, chunk),
                        )
                        command, cwd = self._build_managed_command(provider, python)
                        self._append(install_id, f"$ {python.name} -m pip install {' '.join(provider.python_install_packages)}\n")
                    else:
                        command, cwd = self._build_command(provider, root)
                        self._update(
                            install_id, state="running", message="Installation des dépendances Python…", started_at=_now(),
                        )
                        self._append(install_id, f"$ {' '.join(command)}\n")
                    process = subprocess.Popen(
                        command,
                        cwd=str(cwd),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
                    )
                    assert process.stdout is not None
                    for line in process.stdout:
                        self._append(install_id, line)
                    returncode = process.wait()
                importlib.invalidate_caches()
                if returncode == 0:
                    if frozen:
                        refresh_managed_provider_metadata(root)
                        record_installed_provider(root, provider.id, tuple(provider.python_install_packages))
                    self._update(
                        install_id, state="succeeded", message="Installation terminée.", returncode=returncode,
                        finished_at=_now(), restart_required=provider.restart_after_python_install or frozen,
                    )
                else:
                    self._update(
                        install_id, state="failed", message=f"pip a échoué (code {returncode}). Consultez le journal ci-dessous.",
                        returncode=returncode, finished_at=_now(),
                    )
        except Exception as exc:  # report setup, download and package errors to both interfaces
            self._append(install_id, f"\nErreur d’installation : {type(exc).__name__}: {exc}\n")
            self._update(
                install_id, state="failed", message=f"Installation impossible : {exc}", finished_at=_now(),
            )

