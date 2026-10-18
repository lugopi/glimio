from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
import os
import queue
import subprocess
import tempfile
import shutil
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from seance.audio import _soundcard, audio_com_apartment, record
from seance.layout import get_audio_path, get_transcript_path, has_audio
from seance.pipeline import minutes_folder, process_folder, transcribe_folder
from seance.llm import (
    LLMCancelled, LLMError, run_completion_resilient,
)

from .project_paths import discover_project_root, resolve_session_root
from .services.library import (
    describe_session, list_sessions, list_sessions_page, read_artifact,
    resolve_session_folder, retrieve_passages,
)
from .services.sqlite_db import SQLiteDatabase, database_path
from .services.job_store import JobStore
from .services.preferences_store import PreferencesStore
from .services.search_synthesis import (
    _clean_search_answer,
    _has_unknown_citations,
    _looks_like_malformed_synthesis,
    generate_search_synthesis as _generate_search_synthesis_impl,
)

# Resolve paths from the source package and project markers, not only from cwd.
# This matters for editable installs in a src/ layout and console-script launches.
PROJECT_ROOT = discover_project_root(package_file=__file__)
SESSION_ROOT = resolve_session_root(PROJECT_ROOT)

WEB_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = WEB_DIR / "frontend"
# The Angular application is the only UI. Its production build lives outside the
# source tree, at <project root>/dist/glimio-web-ui, and is served directly.
ANGULAR_DIST_DIR = PROJECT_ROOT / "dist" / "glimio-web-ui"


def _npm_command(args: list[str]) -> list[str]:
    """Return a subprocess command for npm on Windows (npm is an .cmd shim)."""
    if os.name == "nt":
        return ["cmd", "/c", "npm", *args]
    return ["npm", *args]


def _install_frontend_dependencies() -> None:
    """Install front-end dependencies before building (no manual npm step needed)."""
    node_modules = FRONTEND_DIR / "node_modules"
    lock = FRONTEND_DIR / "package-lock.json"
    pkg = FRONTEND_DIR / "package.json"
    needs_install = not node_modules.is_dir()
    if not needs_install and pkg.is_file() and node_modules.is_dir():
        mtime_node = node_modules.stat().st_mtime
        newest_source = max(
            (p.stat().st_mtime for p in (pkg, lock) if p.is_file()), default=0
        )
        needs_install = newest_source > mtime_node
    if needs_install:
        print("[web] Installation des dépendances du front (npm)…", flush=True)
        commands = [["ci"] if lock.is_file() else ["install"], ["install"]]
        last_error: Exception | None = None
        for args in commands:
            try:
                subprocess.run(_npm_command(args), cwd=FRONTEND_DIR, check=True)
                return
            except (OSError, subprocess.CalledProcessError) as exc:
                last_error = exc
        raise SystemExit(f"Impossible d'installer les dépendances du front : {last_error}")


def _build_frontend() -> None:
    print("[web] Build du front Angular (npm run build)…", flush=True)
    cache = FRONTEND_DIR / ".angular"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)
    try:
        subprocess.run(_npm_command(["run", "build"]), cwd=FRONTEND_DIR, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"Le build Angular a échoué : {exc}\n"
            "Vérifiez que Node.js (>= 22) et npm sont installés et sur le PATH."
        ) from exc


def _ensure_angular_dist() -> Path:
    """Guarantee the Angular build exists before serving; build it automatically."""
    index_path = ANGULAR_DIST_DIR / "index.html"
    if index_path.is_file():
        return ANGULAR_DIST_DIR
    if not FRONTEND_DIR.is_dir():
        raise SystemExit(
            f"Dossier front introuvable : {FRONTEND_DIR}. Impossible de construire l'UI."
        )
    _install_frontend_dependencies()
    _build_frontend()
    if not index_path.is_file():
        raise SystemExit(
            f"Build terminé mais introuvable : {index_path}. Relancez « npm run build » dans src/web/frontend."
        )
    return ANGULAR_DIST_DIR


def _sources_newer_than_build() -> bool:
    """True when front sources are newer than the current dist output."""
    index_path = ANGULAR_DIST_DIR / "index.html"
    if not index_path.is_file():
        return True
    built_at = index_path.stat().st_mtime
    roots = [FRONTEND_DIR / "src", FRONTEND_DIR / "public",
             FRONTEND_DIR / "angular.json", FRONTEND_DIR / "package.json",
             FRONTEND_DIR / "package-lock.json", FRONTEND_DIR / "tsconfig.app.json"]
    for root in roots:
        if root.is_file():
            if root.stat().st_mtime > built_at:
                return True
        elif root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path.stat().st_mtime > built_at:
                    return True
    return False
DEFAULT_WHISPER_MODEL = "models/asr/model.bin"
DEFAULT_WHISPER_CLI = "bin/asr/whisper-cli.exe"
DEFAULT_GGUF = "models/llm/model.gguf"
DEFAULT_LLAMA_COMPLETION = "bin/llm/llama-completion.exe"
DEFAULT_THREADS = max(1, (os.cpu_count() or 4) // 2)
VALID_FORMATS = {"summary", "auto", "daily", "technical", "formal", "brainstorm"}


def _project_path(value: str | Path) -> str:
    """Resolve a project-relative model/executable path against the detected root."""
    path = Path(value).expanduser()
    return str(path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve())


def _program_path(value: str) -> str:
    """Resolve a command path when it looks like a path; preserve PATH commands such as ffmpeg."""
    text = str(value).strip()
    if not text:
        return text
    path = Path(text).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    if "/" in text or "\\" in text or (PROJECT_ROOT / path).is_file():
        return str((PROJECT_ROOT / path).resolve())
    return text


async def _warm_soundcard_backend_on_server_thread() -> None:
    """Import SoundCard on the server's long-lived event-loop thread on Windows.

    SoundCard initializes a module-level COM helper at import time. Importing it for
    the first time inside a short-lived FastAPI worker can associate that helper with
    the wrong thread. Worker endpoints and capture threads still initialize COM
    independently through audio_com_apartment(). Audio setup failure is left for the
    devices endpoint to report, so a missing audio backend does not prevent browsing
    existing sessions.
    """
    _initialize_persistence()
    if os.name != "nt":
        return
    try:
        _soundcard()
    except Exception as exc:
        print(f"[audio] SoundCard warm-up deferred: {exc}", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _warm_soundcard_backend_on_server_thread()
    yield


app = FastAPI(
    title="Glimio — Audio, transcription et notes", version="0.4.2",
    docs_url="/api/docs", redoc_url=None, lifespan=lifespan,
)
# The Angular SPA is the whole front-end. Resolve its build (auto npm ci + ng build
# on first run) and mount it directly; there is no legacy static folder anymore.
ANGULAR_DIST_DIR = _ensure_angular_dist()


def _angular_file(relative: str) -> Path | None:
    """Resolve a path inside the Angular dist without allowing traversal."""
    candidate = (ANGULAR_DIST_DIR / relative).resolve()
    try:
        candidate.relative_to(ANGULAR_DIST_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


class Settings(BaseModel):
    model: str = DEFAULT_WHISPER_MODEL
    whisper_cli: str = DEFAULT_WHISPER_CLI
    language: str = "auto"
    threads: int = Field(default=DEFAULT_THREADS, ge=1, le=256)
    openvino_device: str | None = None
    ffmpeg: str = "ffmpeg"
    diarize: bool = False
    diarization_segmentation_model: str = "models/diarization/segmentation.onnx"
    diarization_embedding_model: str = "models/diarization/embedding.onnx"
    diarization_num_speakers: int = Field(default=-1, ge=-1, le=256)
    audio_bitrate_kbps: Literal[128, 256, 384, 512, 768] = 256
    diarization_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    gguf: str = DEFAULT_GGUF
    llama_completion: str = DEFAULT_LLAMA_COMPLETION
    context: int = Field(default=16384, ge=2048, le=131072)
    max_tokens: int = Field(default=6000, ge=500, le=32768)
    analysis_tokens: int = Field(default=3500, ge=100, le=32768)
    analysis_retries: int = Field(default=3, ge=0, le=10)
    analysis_max_splits: int = Field(default=6, ge=0, le=12)
    format: str = "auto"
    no_review: bool = False

    def namespace(self, *, folder: str | None = None) -> argparse.Namespace:
        values = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        values["folder"] = folder
        values["directory"] = str(SESSION_ROOT)
        for key in (
            "model", "whisper_cli", "diarization_segmentation_model",
            "diarization_embedding_model", "gguf", "llama_completion",
        ):
            if values.get(key):
                values[key] = _project_path(values[key])
        values["ffmpeg"] = _program_path(values.get("ffmpeg", "ffmpeg"))
        if values["format"] not in VALID_FORMATS:
            raise HTTPException(status_code=422, detail="Format de résumé invalide.")
        if values.get("diarization_num_speakers") == 0:
            raise HTTPException(status_code=422, detail="Le nombre de participants doit être -1 (automatique) ou au moins 1.")
        if values["openvino_device"] not in (None, "", "CPU", "GPU", "NPU"):
            raise HTTPException(status_code=422, detail="Périphérique OpenVINO invalide.")
        if not values["openvino_device"]:
            values["openvino_device"] = None
        return argparse.Namespace(**values)


class SessionSettingsRequest(BaseModel):
    settings: Settings


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class JobRequest(BaseModel):
    action: Literal["transcribe", "summarize", "process"]
    session_id: str
    settings: Settings = Field(default_factory=Settings)
    force: bool = False


class RecordRequest(BaseModel):
    title: str = ""
    microphone: str = ""
    output: str = ""
    capture_microphone: bool = True
    capture_windows: bool = True
    normalize_windows: bool = True
    normalize_windows_max_gain_db: float = Field(default=30.0, ge=0.0, le=30.0)
    auto_transcribe: bool = False
    auto_pv: bool = False
    settings: Settings = Field(default_factory=Settings)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=20)
    settings: Settings = Field(default_factory=Settings)


class UIPreferences(BaseModel):
    theme: Literal["dark", "light", "midnight", "forest"] = "dark"
    microphone: str = Field(default="", max_length=500)
    output: str = Field(default="", max_length=500)
    capture_microphone: bool = True
    capture_windows: bool = True
    normalize_windows: bool = True
    normalize_windows_max_gain_db: float = Field(default=30.0, ge=0.0, le=30.0)
    recording_workflow: Literal["none", "transcribe", "summary"] = "summary"
    import_action: Literal["process", "transcribe"] = "process"


class PreferencesRequest(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    ui: UIPreferences = Field(default_factory=UIPreferences)


STATE_LOCK = threading.RLock()
JOBS: dict[str, dict[str, Any]] = {}
STOP_EVENTS: dict[str, threading.Event] = {}
# Only the audio capture is exclusive. Model work is handled by one serial queue,
# so Whisper/llama.cpp never overlap each other but can run while a new capture is live.
ACTIVE_JOB_ID: str | None = None  # currently recording job (kept for API compatibility)
PROCESSING_JOB_ID: str | None = None
PROCESSING_QUEUE: queue.Queue[tuple[str, Any] | None] = queue.Queue()
PROCESSING_QUEUE_IDS: list[str] = []
PROCESSING_WORKER_LOCK = threading.Lock()
PROCESSING_WORKER_THREAD: threading.Thread | None = None
MAX_JOB_HISTORY = 100
MAX_IMPORT_BYTES = 5 * 1024 * 1024 * 1024
JOB_STORE: JobStore | None = None
PREFERENCES_STORE: PreferencesStore | None = None
PERSISTENCE_RESTORED = False
PERSISTENCE_LOCK = threading.Lock()

# AI library searches are cancellable independently from transcription/recording jobs.
SEARCH_LOCK = threading.RLock()
SEARCHES: dict[str, dict[str, Any]] = {}
SEARCH_CANCEL_EVENTS: dict[str, threading.Event] = {}
ACTIVE_SEARCH_ID: str | None = None
MAX_SEARCH_HISTORY = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if not key.startswith("_")}


def _serialize_model(model: Any) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _persist_job_locked(job: dict[str, Any], *, strict: bool = False) -> None:
    """Persist a job snapshot while the state lock keeps updates ordered."""
    if JOB_STORE is None:
        return
    try:
        JOB_STORE.save(dict(job))
    except Exception as exc:
        if strict:
            raise
        print(f"[persistence] Could not save job {job.get('id')}: {exc}", flush=True)


def _job_payload(job_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        current = JOBS.get(job_id, {})
        payload = current.get("_payload") or {}
        return dict(payload) if isinstance(payload, dict) else {}


def _worker_from_payload(job_id: str) -> Any:
    """Rebuild a worker solely from its durable job description."""
    payload = _job_payload(job_id)
    job = JOBS.get(job_id, {})
    job_type = payload.get("type")
    if job_type == "session":
        action = str(payload.get("action") or job.get("kind") or "process")
        session_id = str(payload.get("session_id") or job.get("session_id") or "")
        if not session_id:
            raise ValueError("La tâche persistée ne contient pas de séance.")
        settings = Settings(**(payload.get("settings") or {}))

        def worker(restored_job_id: str) -> None:
            folder = resolve_session_folder(SESSION_ROOT, session_id)
            _run_session_job(action, folder, settings, restored_job_id)
        return worker
    if job_type == "import":
        return lambda restored_job_id: _run_import_job(restored_job_id)
    raise ValueError("La tâche en attente ne contient pas assez d'informations pour reprendre.")


def _restore_persisted_jobs() -> None:
    """Restore pending work in FIFO order; unfinished captures are never replayed."""
    global PERSISTENCE_RESTORED, ACTIVE_JOB_ID
    if PERSISTENCE_RESTORED or JOB_STORE is None:
        return
    records = JOB_STORE.load_recent(1000)
    with STATE_LOCK:
        JOBS.clear()
        PROCESSING_QUEUE_IDS.clear()
        for job in records:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            state = job.get("state")
            if job.get("kind") == "recording" and state in {"queued", "running", "stopping"}:
                if job.get("phase") == "completed":
                    job.update({"state": "completed", "message": job.get("message") or "Enregistrement terminé", "finished_at": job.get("finished_at") or _now(), "updated_at": _now(), "queue_position": None})
                else:
                    job.update({
                        "state": "error", "phase": "interrupted",
                        "message": "Enregistrement interrompu par l'arrêt du serveur ; vérifiez les fichiers WAV.",
                        "error": "La capture audio ne peut pas être reprise automatiquement après l'arrêt de la machine.",
                        "finished_at": _now(), "updated_at": _now(), "queue_position": None,
                    })
                JOBS[job_id] = job
                _persist_job_locked(job)
                continue
            if state in {"queued", "running", "stopping"}:
                payload = dict(job.get("_payload") or {})
                payload["resume_phase"] = job.get("phase")
                job["_payload"] = payload
                try:
                    # Validate that enough durable information exists before putting work back in the queue.
                    _worker_from_payload_from_record(job)
                    job.update({
                        "state": "queued", "phase": "recovered",
                        "message": "Reprise après redémarrage · en attente de traitement",
                        "started_at": None, "finished_at": None, "error": None,
                    })
                    PROCESSING_QUEUE_IDS.append(job_id)
                except Exception as exc:
                    job.update({
                        "state": "error", "phase": "recovery-error", "message": "Reprise impossible",
                        "error": f"La tâche persistée est incomplète : {exc}", "finished_at": _now(),
                    })
            JOBS[job_id] = job
            _persist_job_locked(job)
        _refresh_queue_positions_locked()
        PERSISTENCE_RESTORED = True
        if ACTIVE_JOB_ID:
            ACTIVE_JOB_ID = None
    for job_id in list(PROCESSING_QUEUE_IDS):
        try:
            worker = _worker_from_payload(job_id)
            PROCESSING_QUEUE.put((job_id, worker))
        except Exception as exc:
            with STATE_LOCK:
                job = JOBS.get(job_id)
                if job:
                    job.update({"state": "error", "phase": "recovery-error", "message": "Reprise impossible", "error": str(exc), "finished_at": _now(), "queue_position": None})
                    if job_id in PROCESSING_QUEUE_IDS:
                        PROCESSING_QUEUE_IDS.remove(job_id)
                    _persist_job_locked(job)
    if PROCESSING_QUEUE_IDS:
        _ensure_processing_worker()


def _worker_from_payload_from_record(job: dict[str, Any]) -> Any:
    """Validate a restored row without requiring it to already exist in JOBS."""
    payload = job.get("_payload") or {}
    if payload.get("type") == "session":
        action = payload.get("action") or job.get("kind")
        session_id = payload.get("session_id") or job.get("session_id")
        if action not in {"transcribe", "summarize", "process"} or not session_id:
            raise ValueError("action ou session_id manquant")
        Settings(**(payload.get("settings") or {}))
        return True
    if payload.get("type") == "import":
        if payload.get("action") not in {"transcribe", "process"} or not payload.get("source_file"):
            raise ValueError("fichier source ou action manquant")
        Settings(**(payload.get("settings") or {}))
        return True
    raise ValueError("type de tâche inconnu")


def _initialize_persistence() -> None:
    global JOB_STORE, PREFERENCES_STORE
    if JOB_STORE is not None and PREFERENCES_STORE is not None:
        return
    with PERSISTENCE_LOCK:
        if JOB_STORE is not None and PREFERENCES_STORE is not None:
            return
        db = SQLiteDatabase(database_path(PROJECT_ROOT))
        db.initialize()
        JOB_STORE = JobStore(db)
        PREFERENCES_STORE = PreferencesStore(db)
        _restore_persisted_jobs()


def _default_preferences() -> dict[str, Any]:
    return {"settings": _serialize_model(Settings()), "ui": _serialize_model(UIPreferences())}


def _get_preferences() -> dict[str, Any]:
    _initialize_persistence()
    saved = PREFERENCES_STORE.get() if PREFERENCES_STORE else None
    if not saved:
        return _default_preferences()
    defaults = _default_preferences()
    try:
        saved_settings = dict(saved.get("settings") or {})
        legacy_paths = {
            "model": (("models/asr/ggml-large-v3.bin",), "models/asr/model.bin"),
            "whisper_cli": (("bin/asr/transcriber.exe", "bin/whisper/whisper-cli.exe"), "bin/asr/whisper-cli.exe"),
            "gguf": (("models/llm/model.gguf",), "models/llm/model.gguf"),
            "llama_completion": (("bin/llm/inference.exe", "bin/llama-cpp/llama-completion.exe"), "bin/llm/llama-completion.exe"),
            "diarization_segmentation_model": (("models/diarization/segmentation/model.onnx",), "models/diarization/segmentation.onnx"),
            "diarization_embedding_model": (("models/diarization/embedding/nemo_en_titanet_small.onnx",), "models/diarization/embedding.onnx"),
        }
        for key, (old_paths, new_path) in legacy_paths.items():
            # Keep an explicitly configured executable if it exists; migrate only known stale defaults.
            old_path = saved_settings.get(key)
            if old_path in old_paths and not (PROJECT_ROOT / old_path).exists():
                saved_settings[key] = new_path
        settings = Settings(**saved_settings)
        ui = UIPreferences(**(saved.get("ui") or {}))
    except Exception as exc:
        print(f"[preferences] Ignoring invalid saved preferences: {exc}", flush=True)
        return defaults
    return {"settings": _serialize_model(settings), "ui": _serialize_model(ui)}


def _active_job() -> dict[str, Any] | None:
    with STATE_LOCK:
        if ACTIVE_JOB_ID and ACTIVE_JOB_ID in JOBS:
            job = JOBS[ACTIVE_JOB_ID]
            if job["state"] in {"running", "stopping"}:
                return job
        return None


def _set_job(job_id: str, **updates: Any) -> None:
    with STATE_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)
            JOBS[job_id]["updated_at"] = _now()
            _persist_job_locked(JOBS[job_id])


def _prune_job_history_locked() -> None:
    """Bound the in-memory job log while never evicting active or queued work."""
    if len(JOBS) <= MAX_JOB_HISTORY:
        return
    for old_id in list(JOBS):
        if old_id == ACTIVE_JOB_ID or old_id == PROCESSING_JOB_ID:
            continue
        if JOBS[old_id].get("state") in {"running", "stopping", "queued"}:
            continue
        JOBS.pop(old_id, None)
        STOP_EVENTS.pop(old_id, None)
        if JOB_STORE is not None:
            try:
                JOB_STORE.delete(old_id)
            except Exception as exc:
                print(f"[persistence] Could not prune job {old_id}: {exc}", flush=True)
        if len(JOBS) <= MAX_JOB_HISTORY:
            break


def _refresh_queue_positions_locked() -> None:
    for position, queued_id in enumerate(PROCESSING_QUEUE_IDS, start=1):
        item = JOBS.get(queued_id)
        if item and item.get("state") == "queued":
            item["queue_position"] = position
            item["message"] = f"Dans la file de traitement · position {position}"
            item["updated_at"] = _now()
            _persist_job_locked(item)


def _processing_queue_loop() -> None:
    """Run all model jobs serially in one worker thread."""
    global PROCESSING_JOB_ID
    while True:
        item = PROCESSING_QUEUE.get()
        if item is None:
            PROCESSING_QUEUE.task_done()
            continue
        job_id, worker = item
        with STATE_LOCK:
            if job_id in PROCESSING_QUEUE_IDS:
                PROCESSING_QUEUE_IDS.remove(job_id)
            job = JOBS.get(job_id)
            _refresh_queue_positions_locked()
            if not job or job.get("state") != "queued":
                PROCESSING_QUEUE.task_done()
                continue
            PROCESSING_JOB_ID = job_id
            job.update({
                "state": "running",
                "phase": "starting",
                "queue_position": None,
                "started_at": _now(),
                "updated_at": _now(),
            })
            _persist_job_locked(job)
        try:
            worker(job_id)
            with STATE_LOCK:
                current = JOBS.get(job_id)
                if current and current.get("state") in {"running", "stopping"}:
                    last_message = current.get("message") or "Traitement terminé"
                    current.update({
                        "state": "completed", "phase": "completed", "message": last_message,
                        "finished_at": _now(), "updated_at": _now(), "queue_position": None,
                    })
                    _persist_job_locked(current)
        except (Exception, SystemExit) as exc:  # Existing CLI modules use SystemExit for expected failures.
            detail = str(exc).strip() or f"Erreur pendant le traitement ({type(exc).__name__})."
            with STATE_LOCK:
                current = JOBS.get(job_id)
                if current:
                    current.update({
                        "state": "error", "phase": "error", "message": "Échec", "error": detail,
                        "finished_at": _now(), "updated_at": _now(), "queue_position": None,
                    })
                    _persist_job_locked(current)
        finally:
            with STATE_LOCK:
                if PROCESSING_JOB_ID == job_id:
                    PROCESSING_JOB_ID = None
                _prune_job_history_locked()
            PROCESSING_QUEUE.task_done()


def _ensure_processing_worker() -> None:
    global PROCESSING_WORKER_THREAD
    with PROCESSING_WORKER_LOCK:
        if PROCESSING_WORKER_THREAD is None or not PROCESSING_WORKER_THREAD.is_alive():
            PROCESSING_WORKER_THREAD = threading.Thread(
                target=_processing_queue_loop, name="glimio-processing-queue", daemon=True
            )
            PROCESSING_WORKER_THREAD.start()


def _enqueue_job(
    kind: str,
    message: str,
    worker: Any,
    *,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Durably add one FIFO processing operation before notifying the worker."""
    _initialize_persistence()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id, "kind": kind, "state": "queued", "phase": "queued",
        "message": message, "session_id": session_id, "created_at": _now(),
        "updated_at": _now(), "started_at": None, "finished_at": None,
        "error": None, "queue_position": None, "_payload": dict(payload or {}),
    }
    with STATE_LOCK:
        JOBS[job_id] = job
        PROCESSING_QUEUE_IDS.append(job_id)
        try:
            _persist_job_locked(job, strict=True)
        except Exception as exc:
            JOBS.pop(job_id, None)
            PROCESSING_QUEUE_IDS.remove(job_id)
            raise HTTPException(status_code=503, detail=f"Impossible de sauvegarder la tâche dans SQLite : {exc}") from exc
        _refresh_queue_positions_locked()
        _prune_job_history_locked()
        # Persistence happens before queue.put(), so a process crash cannot lose accepted work.
        PROCESSING_QUEUE.put((job_id, worker))
        result = _job_public(dict(job))
    _ensure_processing_worker()
    with STATE_LOCK:
        return _job_public(dict(JOBS.get(job_id, result)))


def _start_job(
    kind: str,
    message: str,
    worker: Any,
    *,
    session_id: str | None = None,
    stop_event: threading.Event | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start capture exclusively; all model/import jobs enter the durable FIFO queue."""
    global ACTIVE_JOB_ID
    if kind != "recording":
        return _enqueue_job(kind, message, worker, session_id=session_id, payload=payload)

    _initialize_persistence()
    with STATE_LOCK:
        if _active_job() is not None:
            raise HTTPException(status_code=409, detail="Un enregistrement est déjà en cours. Arrêtez-le avant d'en démarrer un autre.")
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id, "kind": kind, "state": "running", "phase": "preparing",
            "message": message, "session_id": session_id, "created_at": _now(),
            "updated_at": _now(), "started_at": _now(), "finished_at": None,
            "error": None, "queue_position": None, "_payload": {},
        }
        JOBS[job_id] = job
        if stop_event is not None:
            STOP_EVENTS[job_id] = stop_event
        ACTIVE_JOB_ID = job_id
        _persist_job_locked(job)
        _prune_job_history_locked()

    def run_worker() -> None:
        global ACTIVE_JOB_ID
        try:
            worker(job_id)
            with STATE_LOCK:
                state = JOBS.get(job_id, {}).get("state")
                if state in {"running", "stopping"}:
                    last_message = JOBS[job_id].get("message") or "Terminé"
                    JOBS[job_id].update({"state": "completed", "phase": "completed", "message": last_message, "finished_at": _now(), "updated_at": _now()})
                    _persist_job_locked(JOBS[job_id])
        except (Exception, SystemExit) as exc:  # Existing CLI modules use SystemExit for expected failures.
            detail = str(exc).strip() or f"Erreur pendant le traitement ({type(exc).__name__})."
            with STATE_LOCK:
                if job_id in JOBS:
                    JOBS[job_id].update({"state": "error", "phase": "error", "message": "Échec", "error": detail, "finished_at": _now(), "updated_at": _now()})
                    _persist_job_locked(JOBS[job_id])
        finally:
            with STATE_LOCK:
                STOP_EVENTS.pop(job_id, None)
                if ACTIVE_JOB_ID == job_id:
                    ACTIVE_JOB_ID = None
                _prune_job_history_locked()

    threading.Thread(target=run_worker, name=f"glimio-web-{kind}-{job_id}", daemon=True).start()
    return _job_public(dict(job))

def _get_job_or_404(job_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tâche inconnue ou historique expiré.")
        return _job_public(job)


def _device_names() -> dict[str, list[str]]:
    # Import before the scoped initialization: SoundCard initializes its module-level
    # COM helper during import. In the normal Web path it was already warmed up at
    # startup; doing this in the correct order also makes direct calls safe.
    sc = _soundcard()
    # FastAPI executes this synchronous endpoint in a worker thread. COM initialization
    # on the event-loop thread does not carry over to this worker.
    with audio_com_apartment():
        microphones = [str(mic.name) for mic in sc.all_microphones(include_loopback=False)]
        outputs = [str(speaker.name) for speaker in sc.all_speakers()]
    return {"microphones": microphones, "outputs": outputs}


def _run_session_job(action: str, folder: Path, settings: Settings, job_id: str,
                     force: bool = False) -> None:
    """Run a session pipeline with durable checkpoints between model stages.

    ``force`` clears the checkpoint so a stage (e.g. the summary) can be redone
    even when it was already completed for this session.
    """
    payload = _job_payload(job_id)
    checkpoint = None if force else payload.get("checkpoint")

    def publish(message: str) -> None:
        folded = message.casefold()
        if "whisper" in folded or "transcription" in folded:
            phase = "transcribing"
        elif "llm" in folded or "résumé" in folded or "synthèse" in folded:
            phase = "summarizing"
        else:
            phase = "processing"
        _set_job(job_id, session_id=folder.name, state="running", phase=phase, message=message)

    args = settings.namespace(folder=str(folder))

    def save_checkpoint(value: str) -> None:
        current = _job_payload(job_id)
        current.update({"type": "session", "action": action, "session_id": folder.name,
                        "settings": _serialize_model(settings), "checkpoint": value})
        current.pop("resume_phase", None)
        _set_job(job_id, session_id=folder.name, _payload=current)

    if action == "transcribe":
        if checkpoint != "transcribed":
            publish("Préparation de Whisper…")
            transcribe_folder(folder, args, on_status=publish)
            save_checkpoint("transcribed")
    elif action == "summarize":
        if checkpoint != "summarized":
            publish("Préparation de la synthèse locale…")
            minutes_folder(folder, args, on_status=publish)
            save_checkpoint("summarized")
    elif action == "process":
        if checkpoint not in {"transcribed", "summarized"}:
            # If power was lost during Whisper, a partially written transcript must not be
            # mistaken for a completed stage. Otherwise preserve the CLI pipeline's reuse
            # behavior when a valid transcript already existed before this queued task.
            resume_phase = payload.get("resume_phase")
            transcript_path = get_transcript_path(folder)
            should_transcribe = resume_phase == "transcribing" or not transcript_path.is_file()
            if should_transcribe:
                if not has_audio(folder):
                    raise SystemExit(f"Aucune transcription et aucune piste audio exploitable dans {folder}.")
                publish("Transcription absente ou interrompue · lancement de Whisper…")
                transcribe_folder(folder, args, on_status=publish)
            else:
                publish("Transcription existante détectée · réutilisation du texte")
            save_checkpoint("transcribed")
            checkpoint = "transcribed"
        if checkpoint != "summarized":
            publish("Transcription prête · génération du résumé local…")
            minutes_folder(folder, args, on_status=publish)
            save_checkpoint("summarized")
    else:
        raise ValueError(f"Action de traitement inconnue : {action}")
    publish("Traitement terminé · fichiers disponibles dans la séance")


def _run_import_job(job_id: str) -> None:
    """Import and process audio; convert to a session job as soon as import is durable."""
    payload = _job_payload(job_id)
    settings = Settings(**(payload.get("settings") or {}))
    action = str(payload.get("action") or "process")
    session_id = payload.get("session_id")
    if session_id:
        folder = resolve_session_folder(SESSION_ROOT, str(session_id))
    else:
        source_file = Path(str(payload.get("source_file") or "")).expanduser()
        if not source_file.is_file():
            raise FileNotFoundError(f"Fichier importé temporaire introuvable : {source_file}")
        from seance.audio_import import import_audio_file
        display_name = str(payload.get("display_name") or source_file.name)
        _set_job(job_id, state="running", phase="importing", message=f"Import local de {display_name}…")
        folder = import_audio_file(source_file, SESSION_ROOT, ffmpeg=_program_path(settings.ffmpeg))
        _save_session_processing_settings(folder, settings)
        # Persist the destination session before deleting the temporary upload. If the
        # machine stops now, recovery resumes processing from the session instead of importing twice.
        updated_payload = {
            "type": "session", "action": action, "session_id": folder.name,
            "settings": _serialize_model(settings), "checkpoint": None,
        }
        _set_job(job_id, session_id=folder.name, phase="imported", message="Fichier importé ; traitement ajouté à la file…", _payload=updated_payload)
        source_file.unlink(missing_ok=True)
        try:
            source_file.parent.rmdir()
        except OSError:
            pass
    _run_session_job(action, folder, settings, job_id)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(str(ANGULAR_DIST_DIR / "index.html"))


# Catch-all SPA route: serve hashed Angular assets (main-*.js, styles-*.css,
# brand/glimio.svg, …) and fall back to index.html for client-side routes.
# Registered last so every /api/* endpoint above keeps priority.
@app.get("/{spa_path:path}", include_in_schema=False)
def angular_spa(spa_path: str) -> Response:
    if spa_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Ressource introuvable.")
    served = _angular_file(spa_path) if spa_path else None
    if served is not None:
        return FileResponse(str(served))
    fallback = ANGULAR_DIST_DIR / "index.html"
    if not fallback.is_file():
        raise HTTPException(status_code=404, detail="Build Angular indisponible.")
    return FileResponse(str(fallback))


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "session_root": str(SESSION_ROOT),
        "session_root_exists": SESSION_ROOT.is_dir(),
        "offline_local_mode": True,
    }


@app.get("/api/config")
def config() -> dict[str, Any]:
    defaults = Settings()
    return {
        "session_root": str(SESSION_ROOT),
        "session_root_exists": SESSION_ROOT.is_dir(),
        "project_root": str(PROJECT_ROOT),
        "processing_mode": "local",
        "offline_local_mode": True,
        "defaults": _serialize_model(defaults),
        "preferences": _get_preferences(),
        "formats": ["auto", "summary", "daily", "technical", "formal", "brainstorm"],
    }


@app.get("/api/preferences")
def get_preferences() -> dict[str, Any]:
    return _get_preferences()


@app.put("/api/preferences")
def save_preferences(request: PreferencesRequest) -> dict[str, Any]:
    _initialize_persistence()
    result = {"settings": _serialize_model(request.settings), "ui": _serialize_model(request.ui)}
    assert PREFERENCES_STORE is not None
    try:
        PREFERENCES_STORE.save(result)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Impossible d'enregistrer les préférences dans SQLite : {exc}") from exc
    return result


@app.get("/api/devices")
def devices() -> dict[str, list[str]]:
    try:
        return _device_names()
    except (Exception, SystemExit) as exc:
        raise HTTPException(status_code=503, detail=f"Détection des périphériques impossible : {exc}") from exc


def _decorate_session_processing(item: dict[str, Any]) -> dict[str, Any]:
    """Attach the newest job state to a session without changing its files."""
    now = datetime.now(timezone.utc)
    with STATE_LOCK:
        related = [job.copy() for job in JOBS.values() if job.get("session_id") == item.get("id")]
    if not related:
        item["processing"] = None
        return item
    related.sort(
        key=lambda job: (
            job.get("state") in {"running", "stopping", "queued"},
            job.get("updated_at") or "",
            job.get("created_at") or "",
        ),
        reverse=True,
    )
    latest = related[0]
    active = latest.get("state") in {"running", "stopping", "queued"}
    finished_at = latest.get("finished_at")
    if not active and finished_at:
        try:
            age = (now - datetime.fromisoformat(finished_at)).total_seconds()
        except (ValueError, TypeError):
            age = 999999
        if age > 300:
            item["processing"] = None
            return item
    elif not active and not finished_at:
        item["processing"] = None
        return item
    item["processing"] = {
        "job_id": latest.get("id"),
        "kind": latest.get("kind"),
        "state": latest.get("state"),
        "phase": latest.get("phase"),
        "active": active,
        "message": latest.get("message") or "Traitement en cours…",
        "error": latest.get("error"),
        "started_at": latest.get("started_at"),
        "updated_at": latest.get("updated_at"),
        "finished_at": latest.get("finished_at"),
    }
    return item


@app.get("/api/sessions")
def sessions(q: str = "", filter_by: str = "all", limit: str = "25", offset: int = 0) -> dict[str, Any]:
    if filter_by not in {"all", "summary", "transcript", "audio"}:
        raise HTTPException(status_code=422, detail="Filtre invalide.")
    try:
        limit_value = 0 if str(limit).casefold() in {"all", "0"} else int(limit)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Taille de page invalide.") from exc
    if limit_value < 0 or limit_value > 1000 or offset < 0:
        raise HTTPException(status_code=422, detail="Pagination invalide.")
    try:
        items, total = list_sessions_page(
            SESSION_ROOT, query=q, filter_by=filter_by, limit=limit_value, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for item in items:
        _decorate_session_processing(item)
    return {
        "items": items,
        "count": total,
        "page_count": len(items),
        "limit": limit_value or "all",
        "offset": offset,
        "root": str(SESSION_ROOT),
        "root_exists": SESSION_ROOT.is_dir(),
        "project_root": str(PROJECT_ROOT),
    }


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    item = describe_session(folder)
    metadata_path = folder / "metadata" / "seance.json"
    if not metadata_path.is_file():
        metadata_path = folder / "seance.json"
    metadata: dict[str, Any] = {}
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            metadata = value
    except (OSError, json.JSONDecodeError, UnicodeError):
        pass
    item["metadata"] = metadata
    _decorate_session_processing(item)
    item["files"] = {
        "summary": item["summary"],
        "transcript": item["transcript"],
        "audio_tracks": item["audio_tracks"],
        "analysis": (folder / "analysis" / "analyses.md").is_file(),
    }
    return item


def _save_session_processing_settings(folder: Path, settings: Settings) -> dict[str, Any]:
    """Persist the settings last chosen for this session without dropping other metadata."""
    path = _session_metadata_path(folder)
    metadata: dict[str, Any] = {}
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(value, dict):
                metadata = value
        except (OSError, json.JSONDecodeError, UnicodeError):
            metadata = {}
    metadata["processing_settings"] = _serialize_model(settings)
    try:
        _write_metadata_atomically(path, metadata)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Impossible d’enregistrer les options de la séance : {exc}") from exc
    return metadata


def _session_metadata_path(folder: Path) -> Path:
    structured = folder / "metadata" / "seance.json"
    legacy = folder / "seance.json"
    if structured.is_file() or not legacy.is_file():
        return structured
    return legacy


def _write_metadata_atomically(path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, request: RenameSessionRequest) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        active_jobs = [
            job for job in JOBS.values()
            if job.get("session_id") == folder.name and job.get("state") in {"running", "stopping", "queued"}
        ]
    if active_jobs:
        raise HTTPException(
            status_code=409,
            detail="Impossible de renommer une séance pendant son enregistrement ou son traitement.",
        )
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Le titre ne peut pas être vide.")
    if len(title) > 120:
        raise HTTPException(status_code=422, detail="Le titre doit contenir au maximum 120 caractères.")
    metadata_path = _session_metadata_path(folder)
    metadata: dict[str, Any] = {}
    if metadata_path.is_file():
        try:
            value = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("Les métadonnées ne sont pas un objet JSON.")
            metadata = value
        except (OSError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Les métadonnées sont illisibles ; le titre n'a pas été modifié.") from exc
    metadata["title"] = title
    metadata["title_source"] = "user"
    try:
        _write_metadata_atomically(metadata_path, metadata)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Impossible d'enregistrer le titre : {exc}") from exc
    return {"id": session_id, "title": title, "metadata": metadata}


@app.put("/api/sessions/{session_id}/settings")
def save_session_settings(session_id: str, request: SessionSettingsRequest) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    request.settings.namespace(folder=str(folder))  # validate the complete settings contract before persisting it
    metadata = _save_session_processing_settings(folder, request.settings)
    return {"id": session_id, "settings": _serialize_model(request.settings), "metadata": metadata}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        active = [
            job for job in JOBS.values()
            if job.get("session_id") == folder.name and job.get("state") in {"running", "stopping", "queued"}
        ]
    if active:
        raise HTTPException(status_code=409, detail="Impossible de supprimer une séance pendant son enregistrement ou son traitement.")
    # resolve_session_folder validates that this is a direct child of SESSION_ROOT.
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Impossible de supprimer la séance : {exc}") from exc
    return {"deleted": True, "id": session_id}


@app.get("/api/sessions/{session_id}/audio/{filename}")
def session_audio(session_id: str, filename: str, request: Request):
    """Stream an existing WAV track with HTTP Range support for native audio controls."""
    allowed = {"micro.wav", "windows.wav", "audio_import.wav"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Piste audio inconnue.")
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        capture_active = any(
            job.get("kind") == "recording"
            and job.get("session_id") == folder.name
            and job.get("state") in {"running", "stopping"}
            and job.get("phase") in {"preparing", "recording", "finalizing"}
            for job in JOBS.values()
        )
    if capture_active:
        raise HTTPException(
            status_code=409,
            detail="La piste audio sera lisible après la finalisation de l'enregistrement.",
        )

    path = get_audio_path(folder, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier audio introuvable.")

    size = path.stat().st_size
    if size <= 0:
        raise HTTPException(status_code=404, detail="Le fichier audio est vide.")
    range_header = request.headers.get("range")
    start, end, status_code = 0, max(0, size - 1), 200
    headers = {"Accept-Ranges": "bytes", "Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-cache"}
    if range_header:
        import re as _re
        match = _re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or (not match.group(1) and not match.group(2)) or size <= 0:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"})
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
        else:
            suffix_len = int(match.group(2))
            start = max(0, size - suffix_len)
            end = size - 1
        if start >= size or end < start:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"})
        end = min(end, size - 1)
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    length = max(0, end - start + 1)
    headers["Content-Length"] = str(length)

    def stream_file():
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = length
            while remaining > 0:
                chunk = stream.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(stream_file(), status_code=status_code, media_type="audio/wav", headers=headers)


@app.get("/api/sessions/{session_id}/{kind}")
def session_artifact(session_id: str, kind: str) -> dict[str, str]:
    if kind not in {"summary", "transcript"}:
        raise HTTPException(status_code=404, detail="Document inconnu.")
    try:
        return read_artifact(SESSION_ROOT, session_id, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs")
def jobs() -> dict[str, Any]:
    _initialize_persistence()
    with STATE_LOCK:
        records = sorted(JOBS.values(), key=lambda item: item["created_at"], reverse=True)
        running = JOBS.get(PROCESSING_JOB_ID) if PROCESSING_JOB_ID else None
        return {
            "items": [_job_public(item) for item in records[:100]],
            "active": _job_public(JOBS[ACTIVE_JOB_ID]) if ACTIVE_JOB_ID and ACTIVE_JOB_ID in JOBS else None,
            "queue": {
                "waiting": len(PROCESSING_QUEUE_IDS),
                "running": _job_public(running) if running else None,
                "serial": True,
            },
        }


@app.delete("/api/jobs/history")
def clear_job_history() -> dict[str, int]:
    """Delete finished activity records while preserving queued and active work."""
    _initialize_persistence()
    active_states = {"queued", "running", "stopping"}
    deleted = 0
    with STATE_LOCK:
        protected_ids = set(PROCESSING_QUEUE_IDS)
        if ACTIVE_JOB_ID:
            protected_ids.add(ACTIVE_JOB_ID)
        if PROCESSING_JOB_ID:
            protected_ids.add(PROCESSING_JOB_ID)
        for job_id, record in list(JOBS.items()):
            if job_id in protected_ids or record.get("state") in active_states:
                continue
            JOBS.pop(job_id, None)
            STOP_EVENTS.pop(job_id, None)
            if JOB_STORE is not None:
                JOB_STORE.delete(job_id)
            deleted += 1
    return {"deleted": deleted}


@app.delete("/api/jobs/{job_id}")
def delete_job_history_item(job_id: str) -> dict[str, str]:
    """Delete one finished activity record; active work cannot be removed."""
    _initialize_persistence()
    active_states = {"queued", "running", "stopping"}
    with STATE_LOCK:
        record = JOBS.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Activité introuvable.")
        if job_id in PROCESSING_QUEUE_IDS or job_id in {ACTIVE_JOB_ID, PROCESSING_JOB_ID} or record.get("state") in active_states:
            raise HTTPException(status_code=409, detail="Impossible d’effacer une activité en cours ou en attente.")
        JOBS.pop(job_id, None)
        STOP_EVENTS.pop(job_id, None)
        if JOB_STORE is not None:
            JOB_STORE.delete(job_id)
    return {"deleted": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    return _get_job_or_404(job_id)


@app.post("/api/jobs")
def start_session_job(request: JobRequest) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc

    metadata_path = _session_metadata_path(folder)
    try:
        existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.is_file() else {}
    except (OSError, json.JSONDecodeError, UnicodeError):
        existing_metadata = {}
    if not isinstance(existing_metadata, dict) or not isinstance(existing_metadata.get("processing_settings"), dict):
        _save_session_processing_settings(folder, request.settings)

    def worker(job_id: str) -> None:
        _run_session_job(request.action, folder, request.settings, job_id,
                         force=request.force)

    label = {"transcribe": "Transcription lancée", "summarize": "Résumé lancé", "process": "Traitement complet lancé"}[request.action]
    return _start_job(
        request.action, label, worker, session_id=folder.name,
        payload={"type": "session", "action": request.action, "session_id": folder.name,
                 "settings": _serialize_model(request.settings), "checkpoint": None},
    )


@app.post("/api/recording/start")
def start_recording(request: RecordRequest) -> dict[str, Any]:
    if request.settings.format not in VALID_FORMATS:
        raise HTTPException(status_code=422, detail="Format de résumé invalide.")
    if not request.capture_microphone and not request.capture_windows:
        raise HTTPException(status_code=422, detail="Activez au moins une source audio : microphone ou audio Windows.")
    stop_event = threading.Event()
    holder: dict[str, Path] = {}

    def on_session_created(folder: Path) -> None:
        holder["folder"] = folder
        _set_job(job_id_holder["id"], session_id=folder.name, state="running", phase="preparing", message="Séance créée · préparation des captures audio…")

    job_id_holder: dict[str, str] = {}

    def publish_recording_status(message: str) -> None:
        job_id = job_id_holder.get("id")
        folder = holder.get("folder")
        if not job_id:
            return
        folded = message.casefold()
        if "enregistrement en cours" in folded or "capture de " in folded:
            phase = "recording"
        elif "finalisation des pistes wav" in folded or "écriture de micro.wav" in folded or "écriture de windows.wav" in folded:
            phase = "finalizing"
        elif "whisper" in folded or "transcription absente" in folded:
            phase = "transcribing"
        elif "llm" in folded or "résumé" in folded or "transcription prête" in folded:
            phase = "summarizing"
        else:
            phase = "processing"
        state = "stopping" if phase == "finalizing" else "running"
        _set_job(job_id, session_id=folder.name if folder else None, state=state, phase=phase, message=message)

    def worker(job_id: str) -> None:
        job_id_holder["id"] = job_id
        args = request.settings.namespace()
        args.directory = str(SESSION_ROOT)
        args.title = request.title.strip() or None
        args.microphone = request.microphone.strip() or None
        args.output = request.output.strip() or None
        args.capture_microphone = request.capture_microphone
        args.capture_windows = request.capture_windows
        args.normalize_windows = bool(request.normalize_windows and request.capture_windows)
        args.normalize_windows_max_gain_db = request.normalize_windows_max_gain_db
        # Web capture must end as soon as WAVs are finalized. Model work goes to
        # the serial queue so another recording can start while Whisper/llama.cpp run.
        args.auto_transcribe = False
        args.auto_pv = False
        _set_job(job_id, message="Préparation des périphériques audio…")
        record(args, stop_event=stop_event, on_session_created=on_session_created, on_status=publish_recording_status)
        folder = holder.get("folder")
        if folder:
            _save_session_processing_settings(folder, request.settings)
        if folder and (request.auto_pv or request.auto_transcribe):
            action = "process" if request.auto_pv else "transcribe"
            queue_label = "Traitement complet ajouté à la file" if action == "process" else "Transcription ajoutée à la file"
            queued = _enqueue_job(
                action,
                queue_label,
                lambda processing_job_id: _run_session_job(action, folder, request.settings, processing_job_id),
                session_id=folder.name,
                payload={"type": "session", "action": action, "session_id": folder.name,
                         "settings": _serialize_model(request.settings), "checkpoint": None},
            )
            final_message = f"Enregistrement terminé · traitement en file (position {queued.get('queue_position') or 1})"
        else:
            final_message = "Enregistrement terminé · pistes WAV disponibles"
        _set_job(job_id, session_id=folder.name if folder else None, state="running", phase="completed", message=final_message)

    result = _start_job("recording", "Préparation des périphériques audio…", worker, stop_event=stop_event)
    job_id_holder["id"] = result["id"]
    return result


@app.post("/api/recording/stop")
def stop_recording() -> dict[str, Any]:
    active = _active_job()
    if not active or active["kind"] != "recording":
        raise HTTPException(status_code=409, detail="Aucun enregistrement web actif.")
    if active.get("phase") != "recording":
        raise HTTPException(status_code=409, detail="La capture audio est déjà arrêtée ou encore en préparation ; le traitement en cours n'est pas interrompu par ce bouton.")
    with STATE_LOCK:
        event = STOP_EVENTS.get(active["id"])
        if event is None:
            raise HTTPException(status_code=409, detail="L'enregistrement n'accepte plus de demande d'arrêt.")
        event.set()
        JOBS[active["id"]].update({"state": "stopping", "phase": "finalizing", "message": "Arrêt demandé : finalisation des pistes WAV…", "updated_at": _now()})
        _persist_job_locked(JOBS[active["id"]])
        return _job_public(JOBS[active["id"]])


@app.post("/api/import")
async def import_and_process(
    file: UploadFile = File(...),
    settings_json: str = Form("{}"),
    action: Literal["process", "transcribe"] = Form("process"),
) -> dict[str, Any]:
    try:
        raw_settings = json.loads(settings_json)
        settings = Settings(**raw_settings)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Paramètres d'importation invalides : {exc}") from exc
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    upload_dir = SESSION_ROOT / ".web-uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "audio.bin").suffix.lower()
    if not suffix or len(suffix) > 12 or not suffix[1:].isalnum():
        suffix = ".audio"
    file_path: Path | None = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(prefix="import-", suffix=suffix, dir=upload_dir, delete=False) as target:
            file_path = Path(target.name)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_IMPORT_BYTES:
                    target.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Fichier trop volumineux (limite : 5 Go).")
                target.write(chunk)
    finally:
        await file.close()

    if file_path is None or total == 0:
        if file_path:
            file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Fichier vide ou non reçu.")
    display_name = Path(file.filename or "fichier audio").name

    job_payload = {
        "type": "import", "action": action, "source_file": str(file_path),
        "display_name": display_name, "settings": _serialize_model(settings),
    }
    try:
        return _enqueue_job(
            "import", f"Import de {display_name} en préparation",
            _run_import_job, payload=job_payload,
        )
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise


def _search_public(search: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in search.items() if not key.startswith("_")}


def _set_search(search_id: str, **updates: Any) -> None:
    with SEARCH_LOCK:
        if search_id in SEARCHES:
            SEARCHES[search_id].update(updates)
            SEARCHES[search_id]["updated_at"] = _now()


def _finish_search_cancelled(search_id: str) -> None:
    _set_search(
        search_id,
        state="cancelled",
        message="Recherche annulée",
        answer=None,
        llm_error=None,
        finished_at=_now(),
    )


def _generate_search_synthesis(
    query: str,
    passages: list[dict[str, Any]],
    settings: Settings,
    binary: Path,
    model: Path,
    *,
    cancel_event: threading.Event | None = None,
    on_process: Any = None,
    on_progress: Any = None,
) -> tuple[str, bool]:
    """Compatibility entry point; search logic lives in services/search_synthesis.py."""
    return _generate_search_synthesis_impl(
        query, passages, settings, binary, model,
        cancel_event=cancel_event, on_process=on_process, on_progress=on_progress,
        working_directory=PROJECT_ROOT, completion_runner=run_completion_resilient,
    )


def _run_cancellable_search(search_id: str, request: SearchRequest) -> None:
    cancel_event = SEARCH_CANCEL_EVENTS[search_id]
    try:
        _set_search(search_id, message="Recherche des passages pertinents dans les séances…")

        def publish_retrieval_update(items: list[dict[str, Any]], progress: dict[str, int]) -> None:
            if cancel_event.is_set():
                return
            scanned = progress.get("sessions_scanned", 0)
            total = progress.get("sessions_total", 0)
            found = progress.get("passages_found", 0)
            _set_search(
                search_id,
                sources=items,
                sessions_scanned=scanned,
                sessions_total=total,
                passages_found=found,
                message="Recherche des passages dans les séances…",
            )

        passages = retrieve_passages(
            SESSION_ROOT,
            request.query,
            request.top_k,
            on_update=publish_retrieval_update,
            should_stop=cancel_event.is_set,
        )
        with SEARCH_LOCK:
            latest = SEARCHES.get(search_id, {})
            progress_snapshot = {
                "sessions_scanned": latest.get("sessions_scanned", 0),
                "sessions_total": latest.get("sessions_total", 0),
                "passages_found": latest.get("passages_found", len(passages)),
            }
        _set_search(search_id, sources=passages, **progress_snapshot)
        if cancel_event.is_set():
            _finish_search_cancelled(search_id)
            return
        if not passages:
            _set_search(
                search_id,
                state="completed",
                message="Aucun passage pertinent trouvé",
                answer=None,
                sources=[],
                llm_error="Aucun passage ne contient les termes de recherche. Essaie une formulation ou des mots-clés différents.",
                finished_at=_now(),
            )
            return

        settings = request.settings
        binary = Path(settings.llama_completion).expanduser()
        model = Path(settings.gguf).expanduser()
        if not binary.is_absolute():
            binary = PROJECT_ROOT / binary
        if not model.is_absolute():
            model = PROJECT_ROOT / model
        if not binary.is_file() or not model.is_file():
            missing = "exécutable llama.cpp" if not binary.is_file() else "modèle GGUF"
            _set_search(
                search_id,
                state="completed",
                message="Recherche textuelle terminée ; LLM indisponible",
                answer=None,
                llm_error=f"Recherche textuelle effectuée, mais {missing} introuvable. Vérifie les chemins dans les réglages.",
                finished_at=_now(),
            )
            return
        if cancel_event.is_set():
            _finish_search_cancelled(search_id)
            return

        def publish_process(active_process: subprocess.Popen[Any] | None) -> None:
            with SEARCH_LOCK:
                if search_id in SEARCHES:
                    if active_process is None:
                        SEARCHES[search_id].pop("_process", None)
                    else:
                        SEARCHES[search_id]["_process"] = active_process

        def publish_synthesis_progress(message: str) -> None:
            if not cancel_event.is_set():
                _set_search(search_id, message=message)

        try:
            answer, hit_limit = _generate_search_synthesis(
                request.query, passages, settings, binary, model,
                cancel_event=cancel_event,
                on_process=publish_process,
                on_progress=publish_synthesis_progress,
            )
        except LLMCancelled:
            _finish_search_cancelled(search_id)
            return
        except LLMError as exc:
            with SEARCH_LOCK:
                cancelled = cancel_event.is_set()
            if cancelled:
                _finish_search_cancelled(search_id)
            else:
                _set_search(
                    search_id,
                    state="error",
                    message="Échec de la génération locale",
                    answer=None,
                    llm_error=str(exc),
                    finished_at=_now(),
                )
            return

        if cancel_event.is_set():
            _finish_search_cancelled(search_id)
            return
        if hit_limit:
            _set_search(
                search_id,
                state="error",
                message="Synthèse tronquée",
                answer=None,
                llm_error=(
                    "Le modèle a atteint sa limite de génération sans terminer sa réponse. "
                    "Réduis le nombre de passages, augmente le contexte ou vérifie la limite "
                    "de génération prise en charge par ce modèle."
                ),
                finished_at=_now(),
            )
            return
        if _looks_like_malformed_synthesis(answer):
            _set_search(
                search_id,
                state="error",
                message="Synthèse locale de mauvaise qualité",
                answer=None,
                llm_error=(
                    "Le modèle a renvoyé une sortie de raisonnement interne ou répétitive, qui n'a pas été affichée comme résumé. "
                    "La recherche des passages a réussi, mais la qualité de la génération n'est pas suffisante. "
                    "Vérifie que le fichier GGUF est un modèle instruct/chat adapté et que llama.cpp applique son template de conversation."
                ),
                finished_at=_now(),
            )
            return
        if _has_unknown_citations(answer, passages):
            _set_search(
                search_id,
                state="error",
                message="Références de synthèse invalides",
                answer=None,
                llm_error=(
                    "Le modèle a cité une ou plusieurs sources absentes des extraits utilisés. "
                    "La synthèse n'est pas affichée pour éviter des références trompeuses. "
                    "Essaie une nouvelle génération ou vérifie le modèle GGUF."
                ),
                finished_at=_now(),
            )
            return
        _set_search(
            search_id,
            state="completed",
            message="Synthèse terminée",
            answer=answer,
            llm_error=None,
            finished_at=_now(),
        )
    except (Exception, SystemExit) as exc:
        with SEARCH_LOCK:
            cancelled = cancel_event.is_set()
        if cancelled:
            _finish_search_cancelled(search_id)
        else:
            _set_search(
                search_id,
                state="error",
                message="La recherche a échoué",
                answer=None,
                llm_error=str(exc).strip() or f"Erreur pendant la recherche ({type(exc).__name__}).",
                finished_at=_now(),
            )
    finally:
        global ACTIVE_SEARCH_ID
        with SEARCH_LOCK:
            if search_id in SEARCHES:
                SEARCHES[search_id].pop("_process", None)
            SEARCH_CANCEL_EVENTS.pop(search_id, None)
            if ACTIVE_SEARCH_ID == search_id:
                ACTIVE_SEARCH_ID = None
            if len(SEARCHES) > MAX_SEARCH_HISTORY:
                for old_id in list(SEARCHES):
                    if old_id != ACTIVE_SEARCH_ID and SEARCHES[old_id].get("state") not in {"running", "cancelling"}:
                        SEARCHES.pop(old_id, None)
                        if len(SEARCHES) <= MAX_SEARCH_HISTORY:
                            break


@app.post("/api/search/start")
def start_library_search(request: SearchRequest) -> dict[str, Any]:
    """Start a local AI search in the background so the UI can cancel it."""
    global ACTIVE_SEARCH_ID
    with SEARCH_LOCK:
        if ACTIVE_SEARCH_ID and ACTIVE_SEARCH_ID in SEARCHES and SEARCHES[ACTIVE_SEARCH_ID].get("state") in {"running", "cancelling"}:
            raise HTTPException(status_code=409, detail="Une recherche IA est déjà en cours.")
        search_id = uuid.uuid4().hex[:12]
        search = {
            "id": search_id,
            "state": "running",
            "message": "Recherche en préparation…",
            "query": request.query,
            "answer": None,
            "sources": [],
            "llm_error": None,
            "sessions_scanned": 0,
            "sessions_total": 0,
            "passages_found": 0,
            "created_at": _now(),
            "updated_at": _now(),
            "finished_at": None,
            "_process": None,
        }
        SEARCHES[search_id] = search
        SEARCH_CANCEL_EVENTS[search_id] = threading.Event()
        ACTIVE_SEARCH_ID = search_id
    threading.Thread(
        target=_run_cancellable_search,
        args=(search_id, request),
        name=f"glimio-web-search-{search_id}",
        daemon=True,
    ).start()
    return _search_public(search)


@app.get("/api/search/{search_id}")
def get_library_search(search_id: str) -> dict[str, Any]:
    with SEARCH_LOCK:
        search = SEARCHES.get(search_id)
        if search is None:
            raise HTTPException(status_code=404, detail="Recherche inconnue ou historique expiré.")
        return _search_public(search)


@app.post("/api/search/{search_id}/cancel")
def cancel_library_search(search_id: str) -> dict[str, Any]:
    with SEARCH_LOCK:
        search = SEARCHES.get(search_id)
        if search is None:
            raise HTTPException(status_code=404, detail="Recherche inconnue ou historique expiré.")
        if search.get("state") not in {"running", "cancelling"}:
            return _search_public(search)
        cancel_event = SEARCH_CANCEL_EVENTS.get(search_id)
        if cancel_event is not None:
            cancel_event.set()
        search.update({"state": "cancelling", "message": "Annulation en cours…", "updated_at": _now()})
        process = search.get("_process")
        public = _search_public(search)
    if process is not None:
        try:
            if process.poll() is None:
                process.terminate()
        except OSError:
            pass
    return public


@app.post("/api/search/ask")
def ask_library(request: SearchRequest) -> dict[str, Any]:
    passages = retrieve_passages(SESSION_ROOT, request.query, request.top_k)
    if not passages:
        return {"query": request.query, "answer": None, "sources": [], "llm_error": "Aucun passage ne contient les termes de recherche. Essaie une formulation ou des mots-clés différents."}

    settings = request.settings
    binary = Path(settings.llama_completion).expanduser()
    model = Path(settings.gguf).expanduser()
    if not binary.is_absolute():
        binary = PROJECT_ROOT / binary
    if not model.is_absolute():
        model = PROJECT_ROOT / model
    if not binary.is_file() or not model.is_file():
        missing = "exécutable llama.cpp" if not binary.is_file() else "modèle GGUF"
        return {"query": request.query, "answer": None, "sources": passages, "llm_error": f"Recherche textuelle effectuée, mais {missing} introuvable. Vérifie les chemins dans les réglages."}
    try:
        answer, hit_limit = _generate_search_synthesis(
            request.query, passages, settings, binary, model,
        )
    except LLMError as exc:
        return {"query": request.query, "answer": None, "sources": passages, "llm_error": str(exc)}
    if hit_limit:
        return {
            "query": request.query, "answer": None, "sources": passages,
            "llm_error": "Le modèle a atteint sa limite de génération même après une synthèse par morceaux.",
        }
    answer = _clean_search_answer(answer)
    if not answer:
        return {"query": request.query, "answer": None, "sources": passages, "llm_error": "Le modèle n'a renvoyé aucun texte exploitable."}
    if _looks_like_malformed_synthesis(answer):
        return {
            "query": request.query,
            "answer": None,
            "sources": passages,
            "llm_error": (
                "Le modèle a renvoyé une sortie de raisonnement interne ou répétitive, qui n'a pas été affichée comme résumé. "
                "Vérifie que le GGUF est un modèle instruct/chat et que llama.cpp applique son template de conversation."
            ),
        }
    if _has_unknown_citations(answer, passages):
        return {
            "query": request.query,
            "answer": None,
            "sources": passages,
            "llm_error": (
                "Le modèle a cité une ou plusieurs sources absentes des extraits utilisés. "
                "La synthèse n'est pas affichée pour éviter des références trompeuses."
            ),
        }
    return {"query": request.query, "answer": answer, "sources": passages, "llm_error": None}


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit('Dépendances web absentes. Installe-les avec : python -m pip install -e ".[web]"') from exc
    host = os.environ.get("GLIMIO_WEB_HOST", os.environ.get("SEANCE_WEB_HOST", "127.0.0.1"))
    try:
        port = int(os.environ.get("GLIMIO_WEB_PORT", os.environ.get("SEANCE_WEB_PORT", "8765")))
    except ValueError as exc:
        raise SystemExit("GLIMIO_WEB_PORT (ou SEANCE_WEB_PORT) doit être un entier.") from exc
    # Keep the served UI fresh: rebuild when sources changed (or when forced).
    try:
        if os.environ.get("GLIMIO_WEB_BUILD", "").casefold() in {"1", "true", "yes"} or _sources_newer_than_build():
            _install_frontend_dependencies()
            _build_frontend()
    except SystemExit as exc:
        print(f"[web] {exc}", flush=True)
        raise
    global ANGULAR_DIST_DIR
    ANGULAR_DIST_DIR = _ensure_angular_dist()

    url = f"http://{host}:{port}"
    print(f"Glimio Web : {url}", flush=True)
    print(f"Racine du projet : {PROJECT_ROOT}", flush=True)
    print(f"Dossier des séances : {SESSION_ROOT} (existe : {SESSION_ROOT.is_dir()})", flush=True)
    if os.environ.get("GLIMIO_WEB_OPEN_BROWSER", os.environ.get("SEANCE_WEB_OPEN_BROWSER", "1")).casefold() not in {"0", "false", "no"}:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
