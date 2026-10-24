"""Safe, opt-in installation of built-in provider Python extras.

The web API never accepts package names or shell snippets from callers. It only
uses installation metadata declared on the trusted provider catalog.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import importlib
import os
import re
import subprocess
import sys
import threading
import uuid
from typing import Any, Literal

from seance.providers.contracts import ProviderInfo

InstallState = Literal["queued", "running", "succeeded", "failed"]
_EXTRA_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    """Run one allow-listed pip installation at a time and expose polling status."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pip_lock = threading.Lock()
        self._records: dict[str, _InstallRecord] = {}

    def start(
        self,
        provider: ProviderInfo,
        *,
        project_root: str | Path,
        frozen: bool = False,
    ) -> dict[str, Any]:
        if not (provider.python_install_extra or provider.python_install_packages):
            raise ValueError(f"Le provider {provider.id} ne déclare aucune dépendance Python installable automatiquement.")
        if frozen or getattr(sys, "frozen", False):
            raise RuntimeError(
                "L’installation Python en un clic n’est pas disponible dans la version empaquetée. "
                "Installez les dépendances dans l’environnement Python utilisé par Glimio, puis redémarrez l’application."
            )
        if provider.python_install_extra and not _EXTRA_PATTERN.fullmatch(provider.python_install_extra):
            raise ValueError("Nom d’extra Python invalide dans les métadonnées du provider.")
        packages = tuple(provider.python_install_packages)
        if any(not item or item.startswith("-") or any(ch in item for ch in "\n\r\x00") for item in packages):
            raise ValueError("Liste de paquets déclarée invalide.")

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
            args=(record.id, provider, root),
            name=f"glimio-provider-install-{provider.id}",
            daemon=True,
        )
        thread.start()
        return self.get(record.id) or record.to_dict()

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

    def _build_command(self, provider: ProviderInfo, root: Path) -> tuple[list[str], Path]:
        pyproject = root / "pyproject.toml"
        if provider.python_install_extra and pyproject.is_file():
            if not _EXTRA_PATTERN.fullmatch(provider.python_install_extra):
                raise RuntimeError("Nom d’extra Python invalide dans les métadonnées du provider.")
            requirement = f".[{provider.python_install_extra}]"
            return [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-e", requirement], root
        if provider.python_install_packages:
            return [
                sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                *provider.python_install_packages,
            ], root
        raise RuntimeError(
            "Le projet source pyproject.toml est introuvable et aucun paquet de repli n’est déclaré pour ce provider."
        )

    def _run(self, install_id: str, provider: ProviderInfo, root: Path) -> None:
        self._update(install_id, state="queued", message="En attente du verrou d’installation Python…")
        try:
            # pip cannot safely modify the same environment concurrently.
            with self._pip_lock:
                command, cwd = self._build_command(provider, root)
                self._update(
                    install_id,
                    state="running",
                    message="Installation des dépendances Python…",
                    started_at=_now(),
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
                message = "Installation terminée."
                self._update(
                    install_id,
                    state="succeeded",
                    message=message,
                    returncode=returncode,
                    finished_at=_now(),
                    restart_required=provider.restart_after_python_install,
                )
            else:
                self._update(
                    install_id,
                    state="failed",
                    message=f"pip a échoué (code {returncode}). Consultez le journal ci-dessous.",
                    returncode=returncode,
                    finished_at=_now(),
                )
        except Exception as exc:  # show setup errors in the UI instead of silently failing
            self._append(install_id, f"\nErreur d’installation : {type(exc).__name__}: {exc}\n")
            self._update(
                install_id,
                state="failed",
                message=f"Installation impossible : {exc}",
                finished_at=_now(),
            )
