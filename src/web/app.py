from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import importlib.util
import multiprocessing as mp
import os
import queue
import subprocess
import tempfile
import shutil
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from seance.media.audio import _soundcard, audio_com_apartment, record
from seance.layout import get_audio_path, get_transcript_path, has_audio, list_audio_paths
from seance.processing.pipeline import minutes_folder, process_folder, transcribe_folder, translate_summary_folder
from seance.processing.report_formats import REPORT_FORMATS
from seance.processing.quality_profiles import apply_processing_profile, PROFILE_GENERATION_SETTINGS
from seance.llm import (
    LLMCancelled, LLMError, run_completion_resilient,
)
from seance.project_paths import DEFAULT_LLAMA_COMPLETION_PATH, DEFAULT_WHISPER_CLI_PATH
from seance.summary_languages import TRANSLATION_LANGUAGE_CODES, available_summary_translations, summary_translation_path
from seance.providers import (
    DEFAULT_DIARIZATION_PROVIDER, DIARIZATION_PROVIDER_IDS,
    DEFAULT_TEXT_PROVIDER, DEFAULT_TRANSCRIPTION_PROVIDER,
    TEXT_PROVIDER_IDS, TRANSCRIPTION_PROVIDER_IDS, default_provider_options,
    get_provider_info, get_provider_statuses, normalize_provider_options,
)
from seance.providers.media_tools import (
    DEFAULT_MEDIA_PROVIDER, MEDIA_PROVIDER_IDS, ensure_media_toolchain_ready,
)
from seance.providers.contracts import MediaToolchainUnavailable
from seance.providers.plugins import get_provider_plugin
from seance.providers.options import resolve_provider_option_paths

from seance.project_paths import discover_project_root, resolve_session_root
from seance.core.library import (
    describe_session, list_sessions, list_sessions_page,
    resolve_session_folder, retrieve_passages, summary_path, transcript_path,
)
from seance.core.sqlite_db import SQLiteDatabase, database_path
from seance.core.job_store import JobStore
from seance.core.preferences_store import PreferencesStore
from seance.core.devices import list_audio_devices
from seance.core.sessions import (
    SessionServiceError, get_session as get_core_session,
    read_metadata as read_core_metadata,
    write_metadata as write_core_metadata,
    mark_audio_outputs_stale as mark_core_audio_outputs_stale,
    rename_session as rename_core_session, delete_session as delete_core_session,
    set_audio_track_disabled as set_core_audio_track_disabled,
    delete_audio_track as delete_core_audio_track,
    save_processing_settings as save_core_processing_settings,
    save_summary as save_core_summary,
)
from seance.providers.installer import ProviderInstallManager, python_install_runtime_available
from seance.core.search_synthesis import (
    _clean_search_answer,
    _has_unknown_citations,
    _looks_like_malformed_synthesis,
    generate_search_synthesis as _generate_search_synthesis_impl,
)

# Resolve paths from the source package and project markers, not only from cwd.
# This matters for editable installs in a src/ layout and console-script launches.
PROJECT_ROOT = discover_project_root(package_file=__file__)
SESSION_ROOT = resolve_session_root(PROJECT_ROOT)
_PROVIDER_INSTALLER = ProviderInstallManager()

WEB_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = WEB_DIR / "frontend"
# The Angular application is the only UI. Its production build lives outside the
# source tree, at <project root>/dist/glimio-web-ui, and is served directly.
if os.environ.get("GLIMIO_ANGULAR_DIST_DIR"):
    ANGULAR_DIST_DIR = Path(os.environ["GLIMIO_ANGULAR_DIST_DIR"]).expanduser().resolve()
elif getattr(sys, "frozen", False):
    ANGULAR_DIST_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "angular"
else:
    ANGULAR_DIST_DIR = PROJECT_ROOT / "dist" / "glimio-web-ui"


def _npm_command(args: list[str]) -> list[str]:
    """Return a subprocess command for npm on Windows (npm is an .cmd shim)."""
    if os.name == "nt":
        return ["cmd", "/c", "npm", *args]
    return ["npm", *args]


def _install_frontend_dependencies() -> None:
    """Install front-end dependencies before building (no manual npm step needed)."""
    if shutil.which("npm") is None:
        raise SystemExit(
            "npm est introuvable sur le PATH. Installez Node.js 26.12.1 ou une version compatible avec Angular 22 "
            "(voir les plages de versions dans package.json), puis relancez Glimio."
        )
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
    if not needs_install:
        return
    print("[web] Installation des dépendances du front (npm)…", flush=True)
    commands = [["ci"], ["install"]] if lock.is_file() else [["install"], ["install"]]
    last_error: Exception | None = None
    for step, args in enumerate(commands):
        try:
            subprocess.run(_npm_command(args), cwd=FRONTEND_DIR, check=True)
            return
        except FileNotFoundError as exc:
            raise SystemExit(
                "npm est introuvable sur le PATH. Installez Node.js 26.12.1 ou une version compatible avec Angular 22 "
                "(voir les plages de versions dans package.json), puis relancez Glimio."
            ) from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            last_error = exc
            if step == 0 and len(commands) > 1:
                print("[web] Première tentative npm échouée · nouvelle tentative en cours…",
                      flush=True)
    raise SystemExit(
        f"Impossible d'installer les dépendances du front : {last_error}\n"
        f"L'étape « npm {' '.join(commands[-1])} » a été tentée dans {FRONTEND_DIR} ; "
        "vérifiez Node.js, npm et package-lock.json, puis relancez."
    )


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
            "Vérifiez que Node.js 26.12.1 (ou une version compatible indiquée dans package.json) et npm sont installés et sur le PATH."
        ) from exc


def _ensure_angular_dist() -> Path:
    """Guarantee the Angular build exists before serving; build it automatically."""
    index_path = ANGULAR_DIST_DIR / "index.html"
    if index_path.is_file():
        return ANGULAR_DIST_DIR
    if getattr(sys, "frozen", False):
        raise SystemExit(f"Frontend Glimio empaqueté introuvable : {index_path}")
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
DEFAULT_WHISPER_CLI = DEFAULT_WHISPER_CLI_PATH
DEFAULT_GGUF = "models/llm/model.gguf"
DEFAULT_LLAMA_COMPLETION = DEFAULT_LLAMA_COMPLETION_PATH
DEFAULT_THREADS = max(1, (os.cpu_count() or 4) // 2)
VALID_FORMATS = set(REPORT_FORMATS)


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


def _warm_soundcard_backend_on_server_thread() -> None:
    """Import SoundCard on the server's long-lived event-loop thread on Windows.

    SoundCard initializes a module-level COM helper at import time. Importing it for
    the first time inside a short-lived FastAPI worker can associate that helper with
    the wrong thread. Worker endpoints and capture threads still initialize COM
    independently through audio_com_apartment(). Audio setup failure is left for the
    devices endpoint to report, so a missing audio backend does not prevent browsing
    existing sessions.
    """
    if os.name != "nt":
        return
    try:
        _soundcard()
    except Exception as exc:
        print(f"[audio] SoundCard warm-up deferred: {exc}", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Persistence first: pending jobs are re-queued and the saved session
    # directory is applied before any request arrives. It stays here, as a
    # no-op when main() already ran it, so ASGI/lifespan starts (uvicorn
    # web.app:app) are initialized too.
    _warmup_persistence()
    _warm_soundcard_backend_on_server_thread()
    yield


app = FastAPI(
    title="Glimio — Audio, transcription et notes", version="0.5.0",
    docs_url="/api/docs", redoc_url=None, lifespan=lifespan,
)
# Keep module imports side-effect free: tests and tooling may import the API without
# Node.js installed. ``main()`` ensures the Angular build before starting the server.
# The Angular SPA is mounted from ``dist/glimio-web-ui``; there is no legacy UI.


def _angular_file(relative: str) -> Path | None:
    """Resolve a path inside the Angular dist without allowing traversal."""
    candidate = (ANGULAR_DIST_DIR / relative).resolve()
    try:
        candidate.relative_to(ANGULAR_DIST_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


class Settings(BaseModel):
    processing_profile: Literal["turbo", "balanced", "quality", "pixel-perfect", "custom"] = "balanced"
    model: str = DEFAULT_WHISPER_MODEL
    transcription_provider: str = "whisper.cpp"
    media_provider: str = DEFAULT_MEDIA_PROVIDER
    audio_enhancement_provider: str = "ffmpeg-denoise"
    source_separation_provider: str = "no-separation"
    speaker_embedding_provider: str = "speechbrain-ecapa"
    provider_options: dict[str, dict[str, Any]] = Field(default_factory=dict)
    whisper_cli: str = DEFAULT_WHISPER_CLI
    language: str = "auto"
    summary_language: str = Field(default="auto", pattern="^(auto|fr|en|de|it|es|pt|nl)$")
    threads: int = Field(default=DEFAULT_THREADS, ge=1, le=256)
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    diarize: bool = False
    diarization_provider: str = DEFAULT_DIARIZATION_PROVIDER
    diarization_segmentation_model: str = "models/diarization/segmentation/segmentation.onnx"
    diarization_embedding_model: str = "models/diarization/embedding/embedding.onnx"
    diarization_num_speakers: int = Field(default=-1, ge=-1, le=256)
    audio_bitrate_kbps: Literal[128, 256, 384, 512, 768] = 256
    diarization_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    gguf: str = DEFAULT_GGUF
    text_provider: str = "llama.cpp"
    llama_completion: str = DEFAULT_LLAMA_COMPLETION
    context: int = Field(default=16384, ge=2048, le=131072)
    max_tokens: int = Field(default=6000, ge=500, le=32768)
    analysis_tokens: int = Field(default=3500, ge=100, le=32768)
    analysis_retries: int = Field(default=3, ge=0, le=10)
    analysis_max_splits: int = Field(default=6, ge=0, le=12)
    format: str = "auto"
    no_review: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_acceleration_setting(cls, value: Any) -> Any:
        """Migrate historical global Whisper/device/audio options into provider settings."""
        if not isinstance(value, dict):
            return value
        value = dict(value)
        raw_options = value.get("provider_options")
        whisper_options = raw_options.get("whisper.cpp", {}) if isinstance(raw_options, dict) else {}
        whisper_options = whisper_options if isinstance(whisper_options, dict) else {}
        if "audio_enhancement_provider" not in value:
            legacy_enhancement = str(whisper_options.get("speech_enhancement", "auto")).casefold()
            value["audio_enhancement_provider"] = {"off": "no-enhancement", "ffmpeg": "ffmpeg-denoise", "deepfilter": "deepfilternet", "auto": "ffmpeg-denoise"}.get(legacy_enhancement, "ffmpeg-denoise")
        if "source_separation_provider" not in value:
            value["source_separation_provider"] = "no-separation"
        if "speaker_embedding_provider" not in value:
            value["speaker_embedding_provider"] = "speechbrain-ecapa"
        # Keep the top-level media commands aligned with the provider options, which
        # are the only values the settings UI writes.
        raw_options = value.get("provider_options")
        if isinstance(raw_options, dict):
            media_options = raw_options.get("ffmpeg")
            if isinstance(media_options, dict):
                for key in ("ffmpeg", "ffprobe"):
                    configured = media_options.get(key)
                    if isinstance(configured, str) and configured.strip():
                        value[key] = configured.strip()
        if not value.get("openvino_device"):
            return value
        raw_provider_options = value.get("provider_options")
        provider_options = dict(raw_provider_options) if isinstance(raw_provider_options, dict) else {}
        raw_whisper_options = provider_options.get("whisper.cpp")
        whisper_options = dict(raw_whisper_options) if isinstance(raw_whisper_options, dict) else {}
        whisper_options.setdefault("openvino_enabled", True)
        whisper_options.setdefault("openvino_device", value["openvino_device"])
        provider_options["whisper.cpp"] = whisper_options
        value["provider_options"] = provider_options
        value.pop("openvino_device", None)
        return value

    def namespace(self, *, folder: str | None = None) -> argparse.Namespace:
        values = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        if values.get("text_provider") not in TEXT_PROVIDER_IDS:
            raise HTTPException(status_code=422, detail="Provider de génération inconnu.")
        if values.get("transcription_provider") not in TRANSCRIPTION_PROVIDER_IDS:
            raise HTTPException(status_code=422, detail="Provider de transcription inconnu.")
        if values.get("media_provider") not in MEDIA_PROVIDER_IDS:
            raise HTTPException(status_code=422, detail="Provider média inconnu.")
        if values.get("diarization_provider") not in DIARIZATION_PROVIDER_IDS:
            raise HTTPException(status_code=422, detail="Provider de diarisation inconnu.")
        from seance.providers.audio_processing import ENHANCEMENT_PROVIDER_FACTORIES, SEPARATION_PROVIDER_FACTORIES, EMBEDDING_PROVIDER_FACTORIES
        if values.get("audio_enhancement_provider") not in ENHANCEMENT_PROVIDER_FACTORIES:
            raise HTTPException(status_code=422, detail="Provider d’amélioration audio inconnu.")
        if values.get("source_separation_provider") not in SEPARATION_PROVIDER_FACTORIES:
            raise HTTPException(status_code=422, detail="Provider de séparation audio inconnu.")
        if values.get("speaker_embedding_provider") not in EMBEDDING_PROVIDER_FACTORIES:
            raise HTTPException(status_code=422, detail="Provider d’embeddings vocaux inconnu.")
        values["provider_options"] = normalize_provider_options(
            values.get("provider_options", {}), legacy_values=values,
        )
        # Bridge the active provider's declared options into legacy use-case fields
        # only when those fields exist. New plug-ins receive the full provider_options
        # mapping and do not require adding engine-specific branches here.
        active_provider_ids = {
            values["text_provider"], values["transcription_provider"], values["media_provider"],
            values["diarization_provider"], values["audio_enhancement_provider"],
            values["source_separation_provider"], values["speaker_embedding_provider"],
        }
        pending = list(active_provider_ids)
        while pending:
            current_id = pending.pop()
            current_info = get_provider_info(current_id)
            if current_info is None:
                continue
            for dependency in current_info.requires:
                if dependency not in active_provider_ids:
                    active_provider_ids.add(dependency)
                    pending.append(dependency)
        for provider_id in active_provider_ids:
            info = get_provider_info(provider_id)
            if info is None:
                continue
            options = values["provider_options"].get(provider_id, {})
            for option in info.options:
                if option.key in values and option.key in options:
                    values[option.key] = options[option.key]
        media_options = values["provider_options"].get("ffmpeg", {})
        if "ffmpeg" in media_options:
            values["ffmpeg"] = media_options["ffmpeg"]
        if "ffprobe" in media_options:
            values["ffprobe"] = media_options["ffprobe"]
        values["folder"] = folder
        values["directory"] = str(SESSION_ROOT)
        # Normalize legacy top-level settings through the same provider metadata
        # used by the CLI. This keeps asset paths project-relative while allowing
        # executable commands such as ``whisper-cli`` to resolve from PATH.
        legacy_path_provider_ids = {
            "model": (values.get("transcription_provider"), "whisper.cpp"),
            "whisper_cli": (values.get("transcription_provider"), "whisper.cpp"),
            "diarization_segmentation_model": (values.get("diarization_provider"), "sherpa-onnx"),
            "diarization_embedding_model": (values.get("diarization_provider"), "sherpa-onnx"),
            "gguf": (values.get("text_provider"), "llama.cpp"),
            "llama_completion": (values.get("text_provider"), "llama.cpp"),
        }
        for key, (active_provider_id, legacy_provider_id) in legacy_path_provider_ids.items():
            if not values.get(key):
                continue
            info = get_provider_info(str(active_provider_id or ""))
            declared_keys = {option.key for option in info.options} if info else set()
            if key not in declared_keys:
                info = get_provider_info(legacy_provider_id)
            if info and key in {option.key for option in info.options}:
                values[key] = resolve_provider_option_paths(info, {key: values[key]}, PROJECT_ROOT)[key]
            else:
                values[key] = _project_path(values[key])
        for provider_id, options in values["provider_options"].items():
            info = get_provider_info(provider_id)
            if info is None:
                continue
            options.update(resolve_provider_option_paths(info, options, PROJECT_ROOT))
        values["ffmpeg"] = _program_path(values.get("ffmpeg", "ffmpeg"))
        values["ffprobe"] = _program_path(values.get("ffprobe", "ffprobe"))
        if values["format"] not in VALID_FORMATS:
            raise HTTPException(status_code=422, detail="Format de résumé invalide.")
        if values.get("diarization_num_speakers") == 0:
            raise HTTPException(status_code=422, detail="Le nombre de participants doit être -1 (automatique) ou au moins 1.")
        values = apply_processing_profile(values)
        return argparse.Namespace(**values)


class SessionSettingsRequest(BaseModel):
    settings: Settings


class AudioTrackToggleRequest(BaseModel):
    disabled: bool


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class SaveSummaryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)
    revision: str | None = Field(default=None, max_length=100)


class JobRequest(BaseModel):
    action: Literal["transcribe", "summarize", "process", "translate-summary"]
    session_id: str
    settings: Settings = Field(default_factory=Settings)
    force: bool = False


class AudioSourceSelection(BaseModel):
    kind: Literal["microphone", "output"]
    device_id: str = Field(default="", max_length=1000)
    device_name: str = Field(default="", max_length=500)


class AudioDeviceInfo(BaseModel):
    """Stable API representation of a selectable audio endpoint."""

    id: str
    name: str
    key: str


class AudioDevicesResponse(BaseModel):
    """Legacy display-name lists and endpoint records exposed by /api/devices."""

    microphones: list[str]
    outputs: list[str]
    microphone_devices: list[AudioDeviceInfo]
    output_devices: list[AudioDeviceInfo]


class RecordRequest(BaseModel):
    title: str = ""
    # Legacy single-source fields remain supported for older clients/CLI workflows.
    microphone: str = ""
    output: str = ""
    capture_microphone: bool = True
    capture_windows: bool = True
    # New clients can select multiple microphone and loopback endpoints.
    sources: list[AudioSourceSelection] | None = Field(default=None, max_length=16)
    normalize_windows: bool = True
    normalize_windows_max_gain_db: float = Field(default=30.0, ge=0.0, le=30.0)
    auto_transcribe: bool = False
    auto_pv: bool = False
    settings: Settings = Field(default_factory=Settings)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=20)
    settings: Settings = Field(default_factory=Settings)
    session_ids: list[str] = Field(default_factory=list, max_length=100)


class SearchSynthesisRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1, max_length=20)


class UIPreferences(BaseModel):
    theme: Literal["dark", "light", "midnight", "forest", "dracula", "monokai"] = "dark"
    language: Literal["fr", "en"] = "fr"
    session_root: str = Field(default="", max_length=2000)
    microphone: str = Field(default="", max_length=500)
    output: str = Field(default="", max_length=500)
    capture_microphone: bool = True
    capture_windows: bool = True
    audio_sources: list[AudioSourceSelection] = Field(default_factory=list, max_length=16)
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
CANCEL_EVENTS: dict[str, threading.Event] = {}
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
JOB_EVENT_LOCK = threading.Lock()
JOB_EVENT_SUBSCRIBERS: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue[tuple[str, str]]]] = {}
JOB_EVENT_SHUTDOWN = "__server_shutdown__"
# Live updates are coalesced for a short window so a fast-writing document does
# not flood the browser with one SSE message per line. The pending map keeps
# insertion order: an updated key is removed then re-appended, so the flush
# order matches the order in which the last change of each key happened.
JOB_EVENT_COALESCE_SECONDS = 0.12
JOB_EVENT_PENDING: dict[str, tuple[str, str]] = {}
JOB_EVENT_WAKE = threading.Event()
JOB_EVENT_STOP = threading.Event()
JOB_EVENT_FLUSHER: threading.Thread | None = None
JOB_EVENT_FLUSHER_LOCK = threading.Lock()
ARTIFACT_TAIL_CODE_POINTS = 64

# AI library searches are cancellable independently from transcription/recording jobs.
SEARCH_LOCK = threading.RLock()
SEARCHES: dict[str, dict[str, Any]] = {}
SEARCH_CANCEL_EVENTS: dict[str, threading.Event] = {}
ACTIVE_SEARCH_ID: str | None = None
MAX_SEARCH_HISTORY = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _elapsed_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    """Return a non-negative duration between persisted ISO timestamps."""
    if not started_at or not finished_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        finish = datetime.fromisoformat(finished_at)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if finish.tzinfo is None:
            finish = finish.replace(tzinfo=timezone.utc)
        return max(0.0, (finish - start).total_seconds())
    except (TypeError, ValueError):
        return None


def _transition_job_phase_locked(job: dict[str, Any], next_phase: str) -> None:
    """Record the finished phase before starting the next one (STATE_LOCK required)."""
    previous_phase = str(job.get("phase") or "")
    if previous_phase == next_phase:
        return

    transition_at = _now()
    if previous_phase and previous_phase not in {"queued", "completed", "cancelled", "error"}:
        duration = _elapsed_seconds(job.get("phase_started_at"), transition_at)
        if duration is not None and duration > 0:
            history = job.get("phase_history")
            history = list(history) if isinstance(history, list) else []
            history.append({"phase": previous_phase, "duration_seconds": duration})
            # Prevent event payloads and persisted job records from growing without bound.
            job["phase_history"] = history[-40:]

    job["phase"] = next_phase
    job["phase_started_at"] = (
        None if next_phase in {"queued", "completed", "cancelled", "error", "interrupted", "recovery-error"}
        else transition_at
    )


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in job.items() if not key.startswith("_")}
    payload = job.get("_payload")
    if isinstance(payload, dict) and isinstance(payload.get("provider_event"), dict):
        result["provider_event"] = payload["provider_event"]
    return result


def _jobs_response_locked() -> dict[str, Any]:
    records = sorted(JOBS.values(), key=lambda item: item["created_at"], reverse=True)
    active_records = [item for item in records if item.get("state") in {"queued", "running", "stopping"}]
    terminal_records = [item for item in records if item.get("state") not in {"queued", "running", "stopping"}]
    running = JOBS.get(PROCESSING_JOB_ID) if PROCESSING_JOB_ID else None
    return {
        "items": [_job_public(item) for item in [*active_records, *terminal_records[:100]]],
        "active": _job_public(JOBS[ACTIVE_JOB_ID]) if ACTIVE_JOB_ID and ACTIVE_JOB_ID in JOBS else None,
        "queue": {
            "waiting": len(PROCESSING_QUEUE_IDS),
            "running": _job_public(running) if running else None,
            "serial": True,
        },
    }


def _send_job_event_locked(event_name: str, data: str) -> None:
    """Push one serialized event to connected streams. Requires JOB_EVENT_LOCK."""
    if not JOB_EVENT_SUBSCRIBERS:
        return
    for loop, subscriber_queue in list(JOB_EVENT_SUBSCRIBERS.values()):
        def offer(target: asyncio.Queue[tuple[str, str]] = subscriber_queue,
                  event: tuple[str, str] = (event_name, data)) -> None:
            if target.full():
                try:
                    target.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                target.put_nowait(event)
            except asyncio.QueueFull:
                pass
        try:
            loop.call_soon_threadsafe(offer)
        except RuntimeError:
            # The client event loop is shutting down; the stream cleanup removes it.
            pass


def _coalesce_job_event_locked(event_name: str, payload: dict[str, Any], key: str) -> None:
    """Replace a pending event for ``key`` and wake the coalescing flusher.

    Requires JOB_EVENT_LOCK. Updating an existing key re-appends it so the
    pending dict keeps the last-write order used for the flush.
    """
    if not JOB_EVENT_SUBSCRIBERS or JOB_EVENT_STOP.is_set():
        return
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    JOB_EVENT_PENDING.pop(key, None)
    JOB_EVENT_PENDING[key] = (event_name, data)
    _ensure_job_event_flusher()
    JOB_EVENT_WAKE.set()


def _flush_job_events_locked() -> None:
    """Send every pending event in insertion order. Requires JOB_EVENT_LOCK."""
    if not JOB_EVENT_PENDING:
        return
    batch = list(JOB_EVENT_PENDING.values())
    JOB_EVENT_PENDING.clear()
    for event_name, data in batch:
        _send_job_event_locked(event_name, data)


def _flush_job_events() -> None:
    with JOB_EVENT_LOCK:
        _flush_job_events_locked()


def _job_event_flusher_loop() -> None:
    while not JOB_EVENT_STOP.is_set():
        JOB_EVENT_WAKE.wait(1.0)
        if JOB_EVENT_STOP.is_set():
            break
        JOB_EVENT_WAKE.clear()
        if JOB_EVENT_STOP.wait(JOB_EVENT_COALESCE_SECONDS):
            break
        _flush_job_events()


def _ensure_job_event_flusher() -> None:
    """Start the coalescing thread once. Requires JOB_EVENT_LOCK."""
    global JOB_EVENT_FLUSHER
    with JOB_EVENT_FLUSHER_LOCK:
        if JOB_EVENT_FLUSHER is not None and JOB_EVENT_FLUSHER.is_alive():
            return
        JOB_EVENT_STOP.clear()
        JOB_EVENT_FLUSHER = threading.Thread(
            target=_job_event_flusher_loop, name="glimio-job-event-flusher", daemon=True,
        )
        JOB_EVENT_FLUSHER.start()


def _close_job_event_streams() -> None:
    """End open SSE streams before Uvicorn waits for active HTTP connections."""
    with JOB_EVENT_LOCK:
        # Stop coalescing before the final flush so no producer can enqueue an
        # event between the flush and the shutdown marker.
        JOB_EVENT_STOP.set()
        JOB_EVENT_WAKE.set()
        _flush_job_events_locked()
        subscribers = list(JOB_EVENT_SUBSCRIBERS.values())

    for loop, subscriber_queue in subscribers:
        def close_stream(target: asyncio.Queue[tuple[str, str]] = subscriber_queue) -> None:
            # A busy subscriber must still receive the shutdown marker promptly.
            while target.full():
                try:
                    target.get_nowait()
                except asyncio.QueueEmpty:
                    break
            try:
                target.put_nowait((JOB_EVENT_SHUTDOWN, ""))
            except asyncio.QueueFull:
                pass

        try:
            loop.call_soon_threadsafe(close_stream)
        except RuntimeError:
            # The event loop is already closing; the server will cancel its task.
            pass


def _publish_jobs_snapshot() -> None:
    with STATE_LOCK:
        with JOB_EVENT_LOCK:
            # Pending job events describe changes the snapshot already contains;
            # flush them first so a subscriber never sees an older state after it.
            _flush_job_events_locked()
            if not JOB_EVENT_SUBSCRIBERS:
                return
            data = json.dumps(_jobs_response_locked(), ensure_ascii=False, separators=(",", ":"))
            _send_job_event_locked("snapshot", data)


def _serialize_model(model: Any) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _persist_job_locked(job: dict[str, Any], *, strict: bool = False) -> None:
    """Persist a job snapshot while the state lock keeps updates ordered."""
    if JOB_STORE is not None:
        try:
            JOB_STORE.save(dict(job))
        except Exception as exc:
            if strict:
                raise
            print(f"[persistence] Could not save job {job.get('id')}: {exc}", flush=True)
    with JOB_EVENT_LOCK:
        _coalesce_job_event_locked("job", _job_public(job), f"job:{job.get('id')}")


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
                        "started_at": None, "finished_at": None, "phase_started_at": None, "error": None,
                    })
                    CANCEL_EVENTS[job_id] = threading.Event()
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
        if action not in {"transcribe", "summarize", "process", "translate-summary"} or not session_id:
            raise ValueError("action ou session_id manquant")
        Settings(**(payload.get("settings") or {}))
        return True
    if payload.get("type") == "import":
        if payload.get("action") not in {"transcribe", "process"} or not payload.get("source_file"):
            raise ValueError("fichier source ou action manquant")
        Settings(**(payload.get("settings") or {}))
        return True
    raise ValueError("type de tâche inconnu")


def _warmup_persistence() -> None:
    """Create the SQLite database and its schema at startup (idempotent).

    ``database_path`` already creates the parent directory; ``initialize``
    then opens (and therefore creates) the ``.sqlite3`` file itself. Doing
    this eagerly means a fresh clone never sees 404/503 on /api/* because
    the persistence layer was missing.
    """
    try:
        _initialize_persistence()
    except Exception as exc:  # pragma: no cover - defensive startup guard
        print(f"[web] Persistance SQLite indisponible au démarrage : {exc}", flush=True)


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
        _get_preferences()  # Apply a saved session output directory before job recovery.
        _restore_persisted_jobs()


def _default_preferences() -> dict[str, Any]:
    settings = _serialize_model(Settings())
    settings["provider_options"] = normalize_provider_options(
        default_provider_options(), legacy_values=settings,
    )
    return {"settings": settings, "ui": _serialize_model(UIPreferences())}


def _get_preferences() -> dict[str, Any]:
    global SESSION_ROOT
    _initialize_persistence()
    saved = PREFERENCES_STORE.get() if PREFERENCES_STORE else None
    if not saved:
        return _default_preferences()
    defaults = _default_preferences()
    try:
        saved_settings = dict(saved.get("settings") or {})
        legacy_paths = {
            "model": (("models/asr/ggml-large-v3.bin",), "models/asr/model.bin"),
            "whisper_cli": (("bin/asr/transcriber.exe", "bin/whisper/whisper-cli.exe", "bin/asr/whisper-cli.exe", "bin/asr/whisper-cli"), DEFAULT_WHISPER_CLI_PATH),
            "gguf": (("models/llm/model.gguf",), "models/llm/model.gguf"),
            "llama_completion": (("bin/llm/inference.exe", "bin/llama-cpp/llama-completion.exe", "bin/llm/llama-completion.exe", "bin/llm/llama-completion"), DEFAULT_LLAMA_COMPLETION_PATH),
            "diarization_segmentation_model": (("models/diarization/segmentation/model.onnx", "models/diarization/segmentation.onnx"), "models/diarization/segmentation/segmentation.onnx"),
            "diarization_embedding_model": (("models/diarization/embedding/nemo_en_titanet_small.onnx", "models/diarization/embedding.onnx"), "models/diarization/embedding/embedding.onnx"),
        }
        for key, (old_paths, new_path) in legacy_paths.items():
            # Keep an explicitly configured executable if it exists; migrate only known stale defaults.
            old_path = saved_settings.get(key)
            if old_path in old_paths and not (PROJECT_ROOT / old_path).exists():
                saved_settings[key] = new_path
        if saved_settings.get("text_provider") not in TEXT_PROVIDER_IDS:
            saved_settings["text_provider"] = next(iter(TEXT_PROVIDER_IDS), DEFAULT_TEXT_PROVIDER)
        if saved_settings.get("transcription_provider") not in TRANSCRIPTION_PROVIDER_IDS:
            saved_settings["transcription_provider"] = next(iter(TRANSCRIPTION_PROVIDER_IDS), DEFAULT_TRANSCRIPTION_PROVIDER)
        if saved_settings.get("media_provider") not in MEDIA_PROVIDER_IDS:
            saved_settings["media_provider"] = DEFAULT_MEDIA_PROVIDER
        if saved_settings.get("diarization_provider") not in DIARIZATION_PROVIDER_IDS:
            saved_settings["diarization_provider"] = DEFAULT_DIARIZATION_PROVIDER
        settings = Settings(**saved_settings)
        settings_value = _serialize_model(settings)
        settings_value["provider_options"] = normalize_provider_options(
            saved_settings.get("provider_options", {}), legacy_values=saved_settings,
        )
        ui = UIPreferences(**(saved.get("ui") or {}))
        SESSION_ROOT = resolve_session_root(PROJECT_ROOT, ui.session_root or None)
        ui.session_root = str(SESSION_ROOT)
    except Exception as exc:
        print(f"[preferences] Ignoring invalid saved preferences: {exc}", flush=True)
        return defaults
    return {"settings": settings_value, "ui": _serialize_model(ui)}


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
            job = JOBS[job_id]
            if job.get("state") == "stopping" and updates.get("state") == "running":
                updates.pop("state", None)
            next_phase = updates.get("phase")
            if isinstance(next_phase, str) and next_phase != job.get("phase"):
                _transition_job_phase_locked(job, next_phase)
            job.update(updates)
            job["updated_at"] = _now()
            _persist_job_locked(job)


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
        CANCEL_EVENTS.pop(old_id, None)
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
            _transition_job_phase_locked(job, "starting")
            job.update({
                "state": "running",
                "phase": "starting",
                "phase_started_at": job.get("phase_started_at") or _now(),
                "phase_history": list(job.get("phase_history") or []),
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
                    cancelled = CANCEL_EVENTS.get(job_id) is not None and CANCEL_EVENTS[job_id].is_set()
                    terminal_phase = "cancelled" if cancelled else "completed"
                    _transition_job_phase_locked(current, terminal_phase)
                    current.update({
                        "state": "cancelled" if cancelled else "completed",
                        "phase": terminal_phase,
                        "message": "Traitement annulé" if cancelled else last_message,
                        "finished_at": _now(), "updated_at": _now(), "queue_position": None,
                    })
                    _persist_job_locked(current)
        except (Exception, SystemExit) as exc:  # Existing CLI modules use SystemExit for expected failures.
            detail = str(exc).strip() or f"Erreur pendant le traitement ({type(exc).__name__})."
            with STATE_LOCK:
                current = JOBS.get(job_id)
                if current:
                    cancelled = CANCEL_EVENTS.get(job_id) is not None and CANCEL_EVENTS[job_id].is_set()
                    terminal_phase = "cancelled" if cancelled else "error"
                    _transition_job_phase_locked(current, terminal_phase)
                    current.update({
                        "state": "cancelled" if cancelled else "error",
                        "phase": terminal_phase,
                        "message": "Traitement annulé" if cancelled else "Échec",
                        "error": None if cancelled else detail,
                        "finished_at": _now(), "updated_at": _now(), "queue_position": None,
                    })
                    _persist_job_locked(current)
        finally:
            with STATE_LOCK:
                CANCEL_EVENTS.pop(job_id, None)
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
    complete_recording_job_id: str | None = None,
) -> dict[str, Any]:
    """Durably enqueue FIFO work, optionally handing off from a finished recording.

    The completed recording and its follow-up processing job are transitioned under
    the same lock. This prevents the capture job from conflicting with its own
    processing job, while keeping other concurrent requests from slipping into the
    hand-off window.
    """
    _initialize_persistence()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id, "kind": kind, "state": "queued", "phase": "queued",
        "message": message, "session_id": session_id, "created_at": _now(),
        "updated_at": _now(), "started_at": None, "finished_at": None,
        "phase_started_at": None, "phase_history": [],
        "error": None, "queue_position": None, "_payload": dict(payload or {}),
    }
    with STATE_LOCK:
        if session_id and any(
            existing.get("id") != complete_recording_job_id
            and existing.get("session_id") == session_id
            and existing.get("state") in {"queued", "running", "stopping"}
            for existing in JOBS.values()
        ):
            raise HTTPException(status_code=409, detail="Un traitement est déjà en cours pour cette séance.")
        recording_job = None
        if complete_recording_job_id is not None:
            recording_job = JOBS.get(complete_recording_job_id)
            if (
                recording_job is None
                or recording_job.get("kind") != "recording"
                or recording_job.get("session_id") != session_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="L’enregistrement est terminé, mais sa tâche ne permet pas de lancer le traitement automatique.",
                )
        JOBS[job_id] = job
        CANCEL_EVENTS[job_id] = threading.Event()
        PROCESSING_QUEUE_IDS.append(job_id)
        try:
            _persist_job_locked(job, strict=True)
        except Exception as exc:
            JOBS.pop(job_id, None)
            CANCEL_EVENTS.pop(job_id, None)
            PROCESSING_QUEUE_IDS.remove(job_id)
            raise HTTPException(status_code=503, detail=f"Impossible de sauvegarder la tâche dans SQLite : {exc}") from exc
        if recording_job is not None:
            _transition_job_phase_locked(recording_job, "completed")
            recording_job.update({
                "state": "completed",
                "phase": "completed",
                "message": "Enregistrement terminé · ajout du traitement à la file…",
                "finished_at": recording_job.get("finished_at") or _now(),
                "updated_at": _now(),
                "queue_position": None,
            })
            _persist_job_locked(recording_job)
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
            "phase_started_at": _now(), "phase_history": [],
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
                    _transition_job_phase_locked(JOBS[job_id], "completed")
                    JOBS[job_id].update({"state": "completed", "phase": "completed", "message": last_message, "finished_at": _now(), "updated_at": _now()})
                    _persist_job_locked(JOBS[job_id])
        except (Exception, SystemExit) as exc:  # Existing CLI modules use SystemExit for expected failures.
            detail = str(exc).strip() or f"Erreur pendant le traitement ({type(exc).__name__})."
            with STATE_LOCK:
                if job_id in JOBS:
                    _transition_job_phase_locked(JOBS[job_id], "error")
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


def _device_names() -> dict[str, Any]:
    """Web-facing wrapper around the shared audio-device use case."""
    return list_audio_devices(soundcard_loader=_soundcard, com_scope=audio_com_apartment)


def _run_session_job(action: str, folder: Path, settings: Settings, job_id: str,
                     force: bool = False) -> None:
    """Run a session pipeline with durable checkpoints between model stages.

    ``force`` clears the checkpoint so requested stages can be redone even when
    they were already completed. A forced full process reruns transcription and summary.
    """
    payload = _job_payload(job_id)
    checkpoint = None if force else payload.get("checkpoint")

    def publish(message: str) -> None:
        folded = message.casefold()
        if "traitement terminé" in folded:
            phase = "completed"
        elif "réutilisation du texte" in folded:
            phase = "processing"
        elif "traduction du résumé" in folded:
            phase = "translating"
        elif any(term in folded for term in (
            "llm", "analyse", "résumé", "synthèse", "génération", "rédaction", "relecture",
        )):
            phase = "summarizing"
        elif "détection des changements de voix" in folded or "diarisation" in folded:
            phase = "processing" if "terminée" in folded or "terminé" in folded else "diarizing"
        elif "whisper" in folded or "transcription" in folded:
            phase = "transcribing"
        elif "import" in folded:
            phase = "importing"
        elif "préparation" in folded:
            phase = "preparing"
        else:
            phase = "processing"
        _set_job(job_id, session_id=folder.name, state="running", phase=phase, message=message)

    args = settings.namespace(folder=str(folder))
    cancel_event = CANCEL_EVENTS.get(job_id)
    args._cancel_event = cancel_event

    def publish_artifact_update(kind: str) -> None:
        payload: dict[str, Any] = {"session_id": folder.name, "kind": kind}
        live_path = folder / (
            "transcript/transcription_en_cours.md"
            if kind == "transcript"
            else "summary/resume_audio_en_cours.md"
        )
        try:
            stat = live_path.stat()
        except OSError:
            pass
        else:
            payload["revision"] = f"{stat.st_mtime_ns}:{stat.st_size}"
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("artifact", payload, f"artifact:{folder.name}:{kind}")

    args.artifact_event_callback = publish_artifact_update

    def publish_provider_event(event: Any) -> None:
        phase = {
            "transcription": "transcribing",
            "generation": "translating" if action == "translate-summary" else "summarizing",
        }.get(event.task, "translating" if action == "translate-summary" else "processing")
        current = _job_payload(job_id)
        current["provider_event"] = event.to_dict()
        _set_job(job_id, phase=phase, message=event.message, _payload=current)

    args.provider_event_callback = publish_provider_event

    def mark_outputs_current(*, transcript: bool = False, summary: bool = False) -> None:
        metadata = _read_session_metadata(folder)
        if transcript:
            metadata["audio_transcript_stale"] = False
        if summary:
            metadata["audio_summary_stale"] = False
        _write_session_metadata(folder, metadata)

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
            mark_outputs_current(transcript=True)
            save_checkpoint("transcribed")
    elif action == "summarize":
        if checkpoint != "summarized":
            session_metadata = _read_session_metadata(folder)
            if session_metadata.get("audio_transcript_stale"):
                raise SystemExit(
                    "La transcription est signalée comme obsolète après une modification des pistes audio. "
                    "Lancez d’abord la transcription ou le traitement complet avant de régénérer le résumé."
                )
            publish("Préparation de la synthèse locale…")
            minutes_folder(folder, args, on_status=publish)
            mark_outputs_current(summary=True)
            save_checkpoint("summarized")
    elif action == "translate-summary":
        target_language = settings.summary_language
        if target_language == "auto":
            raise SystemExit("Choisissez une langue cible explicite pour traduire le résumé.")
        publish(f"Traduction du résumé en {target_language}…")
        translate_summary_folder(folder, args, target_language=target_language, on_status=publish)
        publish("Traduction du résumé terminée · variante enregistrée")
        save_checkpoint("translated")
    elif action == "process":
        if checkpoint not in {"transcribed", "summarized"}:
            # If power was lost during Whisper, a partially written transcript must not be
            # mistaken for a completed stage. Otherwise preserve the CLI pipeline's reuse
            # behavior when a valid transcript already existed before this queued task.
            resume_phase = payload.get("resume_phase")
            transcript_path = get_transcript_path(folder)
            session_metadata = _read_session_metadata(folder)
            should_transcribe = (force or resume_phase == "transcribing" or not transcript_path.is_file()
                                 or bool(session_metadata.get("audio_transcript_stale")))
            if should_transcribe:
                if not has_audio(folder):
                    raise SystemExit(f"Aucune transcription et aucune piste audio exploitable dans {folder}.")
                publish("Transcription en cours · lancement de Whisper…")
                transcribe_folder(folder, args, on_status=publish)
                mark_outputs_current(transcript=True)
            else:
                publish("Transcription existante détectée · réutilisation du texte")
            save_checkpoint("transcribed")
            checkpoint = "transcribed"
        if checkpoint != "summarized":
            publish("Transcription prête · génération du résumé local…")
            minutes_folder(folder, args, on_status=publish)
            mark_outputs_current(summary=True)
            save_checkpoint("summarized")
    else:
        raise ValueError(f"Action de traitement inconnue : {action}")
    publish("Traitement terminé · fichiers disponibles dans la séance")


def _run_import_job(job_id: str) -> None:
    """Import and process audio; convert to a session job as soon as import is durable."""
    payload = _job_payload(job_id)
    settings = Settings(**(payload.get("settings") or {}))
    action = str(payload.get("action") or "process")
    normalization = payload.get("normalization") or {}
    normalize_audio = bool(normalization.get("enabled", True))
    normalize_max_gain_db = float(normalization.get("max_gain_db", 30.0))
    session_id = payload.get("session_id")
    if session_id:
        folder = resolve_session_folder(SESSION_ROOT, str(session_id))
    else:
        source_file = Path(str(payload.get("source_file") or "")).expanduser()
        if not source_file.is_file():
            raise FileNotFoundError(f"Fichier importé temporaire introuvable : {source_file}")
        from seance.media.audio_import import import_audio_file
        display_name = str(payload.get("display_name") or source_file.name)
        _set_job(job_id, state="running", phase="importing", message=f"Import local de {display_name}…")
        try:
            folder = import_audio_file(
                source_file,
                SESSION_ROOT,
                media_provider=settings.media_provider,
                media_options=settings.provider_options.get(settings.media_provider, {}),
                # Historical keyword arguments keep their meaning for the ffmpeg provider.
                ffmpeg=_program_path(settings.ffmpeg),
                ffprobe=_program_path(settings.ffprobe),
                normalize=normalize_audio,
                max_gain_db=normalize_max_gain_db,
                cancel_event=CANCEL_EVENTS.get(job_id),
            )
        except BaseException:
            # No session owns this upload yet, so never leave the temporary file behind.
            source_file.unlink(missing_ok=True)
            raise
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


# NOTE: this catch-all is re-registered at the END of the module (see below) so
# every /api/* endpoint declared after it keeps priority. The placeholder here
# only documents the SPA fallback contract.
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
    preferences = _get_preferences()
    return {
        "session_root": str(SESSION_ROOT),
        "session_root_exists": SESSION_ROOT.is_dir(),
        "project_root": str(PROJECT_ROOT),
        "processing_mode": "local",
        "offline_local_mode": True,
        "defaults": _default_preferences()["settings"],
        "preferences": preferences,
        "formats": list(REPORT_FORMATS),
        "processing_profiles": PROFILE_GENERATION_SETTINGS,
    }


@app.get("/api/providers")
def providers() -> dict[str, Any]:
    """Return neutral provider metadata and current local readiness to the UI."""
    settings = _get_preferences()["settings"]
    runtime_is_frozen = bool(getattr(sys, "frozen", False))
    pip_available = importlib.util.find_spec("pip") is not None
    runtime_can_install_python = python_install_runtime_available(frozen=runtime_is_frozen)
    payloads = []
    for item in get_provider_statuses(Settings(**settings), project_root=PROJECT_ROOT):
        payload = item.to_dict()
        plugin = get_provider_plugin(item.provider.id)
        is_third_party_plugin = plugin is not None and plugin.info is item.provider
        if is_third_party_plugin:
            # Glimio's managed installer only installs in-tree dependencies;
            # an entry point is code from an independently installed distribution.
            payload["python_install_available"] = False
        payload["python_install_runtime_available"] = bool(
            payload["python_install_available"] and runtime_can_install_python
        )
        payload["python_install_block_reason"] = (
            "Les dépendances de ce provider tiers sont gérées par son paquet Python."
            if is_third_party_plugin else ""
        )
        if payload["python_install_available"] and runtime_is_frozen and not runtime_can_install_python:
            payload["python_install_block_reason"] = (
                "L’installation des providers Python est actuellement prise en charge dans les éditions précompilées "
                "Windows x64 et Linux x86_64 uniquement."
            )
        elif payload["python_install_available"] and not runtime_is_frozen and not pip_available:
            payload["python_install_block_reason"] = (
                "Le module pip n’est pas disponible dans l’environnement Python courant. "
                "Installez/activez pip dans cet environnement puis relancez Glimio."
            )
        payloads.append(payload)
    return {"providers": payloads}


@app.post("/api/providers/{provider_id}/install-python")
def install_provider_python(provider_id: str, request: Request) -> dict[str, Any]:
    """Install only Python dependencies declared by a built-in provider, from localhost."""
    remote_host = request.client.host if request.client else ""
    try:
        import ipaddress
        local_request = ipaddress.ip_address(remote_host).is_loopback
    except ValueError:
        local_request = remote_host.casefold() == "localhost"
    if not local_request:
        raise HTTPException(status_code=403, detail="L’installation des dépendances est autorisée uniquement depuis Glimio sur la machine locale.")
    provider = get_provider_info(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider inconnu.")
    plugin = get_provider_plugin(provider_id)
    if plugin is not None and plugin.info is provider:
        raise HTTPException(status_code=400, detail="Les dépendances d’un provider tiers doivent être gérées par son paquet Python.")
    if not (provider.python_install_extra or provider.python_install_packages):
        raise HTTPException(status_code=400, detail="Ce provider n’a pas de dépendances Python installables en un clic.")
    try:
        install = _PROVIDER_INSTALLER.start(
            provider, project_root=PROJECT_ROOT, frozen=bool(getattr(sys, "frozen", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"install": install}


@app.get("/api/provider-installs/{install_id}")
def provider_python_install_status(install_id: str) -> dict[str, Any]:
    """Poll status of a background Python provider installation."""
    install = _PROVIDER_INSTALLER.get(install_id)
    if install is None:
        raise HTTPException(status_code=404, detail="Installation inconnue ou historique expiré.")
    return {"install": install}


@app.get("/api/preferences")
def get_preferences() -> dict[str, Any]:
    return _get_preferences()


@app.put("/api/preferences")
def save_preferences(request: PreferencesRequest) -> dict[str, Any]:
    global SESSION_ROOT
    _initialize_persistence()
    requested_session_root = resolve_session_root(PROJECT_ROOT, request.ui.session_root or None)
    request.ui.session_root = str(requested_session_root)
    try:
        request.settings.namespace()
        settings_value = _serialize_model(request.settings)
        settings_value["provider_options"] = normalize_provider_options(
            settings_value.get("provider_options", {}), legacy_values=settings_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Options provider invalides : {exc}") from exc
    result = {"settings": settings_value, "ui": _serialize_model(request.ui)}
    assert PREFERENCES_STORE is not None
    try:
        PREFERENCES_STORE.save(result)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Impossible d'enregistrer les préférences dans SQLite : {exc}") from exc
    SESSION_ROOT = requested_session_root
    return result


@app.get("/api/devices", response_model=AudioDevicesResponse)
def devices() -> AudioDevicesResponse:
    try:
        # Do not annotate this response as dict[str, list[str]]: device_* values
        # are structured records, not strings. A typed schema keeps serialization
        # and OpenAPI aligned with the actual contract consumed by Angular.
        return AudioDevicesResponse(**_device_names())
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
    phase = latest.get("phase") or {
        "transcribe": "transcribing", "summarize": "summarizing",
        "process": "processing", "recording": "recording", "import": "importing",
    }.get(latest.get("kind"), "preparing")
    item["processing"] = {
        "job_id": latest.get("id"),
        "kind": latest.get("kind"),
        "state": latest.get("state"),
        "phase": phase,
        "active": active,
        "message": latest.get("message") or "Traitement en cours…",
        "error": latest.get("error"),
        "started_at": latest.get("started_at"),
        "updated_at": latest.get("updated_at"),
        "finished_at": latest.get("finished_at"),
        "phase_started_at": latest.get("phase_started_at"),
        "phase_history": latest.get("phase_history", []),
    }
    return item


def _active_session_artifact_job(session_id: str, kind: str) -> dict[str, Any] | None:
    """Return the active job that is currently replacing a session artifact."""
    expected_phase = {"transcript": "transcribing", "summary": "summarizing"}.get(kind)
    if expected_phase is None:
        return None
    with STATE_LOCK:
        active = [
            job.copy()
            for job in JOBS.values()
            if job.get("session_id") == session_id
            and job.get("state") in {"running", "stopping"}
            and (
                job.get("phase") == expected_phase
                or (kind == "summary" and job.get("kind") == "process"
                    and job.get("phase") in {"transcribing", "diarizing"})
                or (kind == "transcript" and job.get("phase") == "diarizing")
            )
        ]
    if not active:
        return None
    return max(active, key=lambda job: job.get("updated_at") or "")


def _live_session_artifact(folder: Path, session_id: str, kind: str) -> Path | None:
    """Return an in-progress document only while its matching job stage is active."""
    if not _active_session_artifact_job(session_id, kind):
        return None
    preview = folder / ("transcript/transcription_en_cours.md" if kind == "transcript" else "summary/resume_audio_en_cours.md")
    return preview if preview.is_file() else None


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
    item["summary_translations"] = available_summary_translations(folder)
    _decorate_session_processing(item)
    processing = item.get("processing") or {}
    if processing.get("active"):
        if processing.get("phase") in {"transcribing", "diarizing"} and _active_session_artifact_job(session_id, "transcript"):
            # Keep the document tab available, but do not expose an ever-growing
            # or stale transcript while transcription or diarization is running.
            item["transcript"] = True
        if processing.get("kind") == "process" and processing.get("phase") in {"transcribing", "diarizing"}:
            # A complete run will replace the summary using its new transcript.
            # Hide the old summary until generation starts to avoid presenting stale results.
            item["summary"] = False
        if processing.get("phase") == "summarizing" and _live_session_artifact(folder, session_id, "summary"):
            item["summary"] = True
    item["files"] = {
        "summary": item["summary"],
        "transcript": item["transcript"],
        "audio_tracks": item["audio_tracks"],
        "analysis": (folder / "analysis" / "analyses.md").is_file(),
    }
    return item


def _save_session_processing_settings(folder: Path, settings: Settings) -> dict[str, Any]:
    """Persist the settings last chosen for this session without dropping other metadata."""
    try:
        metadata = dict(read_core_metadata(folder))
    except SessionServiceError:
        # An unreadable metadata file must not prevent saving the chosen options.
        metadata = {}
    metadata["processing_settings"] = _serialize_model(settings)
    _write_session_metadata(folder, metadata)
    return metadata


def _read_session_metadata(folder: Path) -> dict[str, Any]:
    try:
        return read_core_metadata(folder)
    except SessionServiceError as exc:
        raise HTTPException(
            status_code=409,
            detail="Les métadonnées de la séance sont illisibles ; aucune piste n’a été modifiée.",
        ) from exc


def _write_session_metadata(folder: Path, metadata: dict[str, Any]) -> None:
    try:
        write_core_metadata(folder, metadata)
    except SessionServiceError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Impossible d’enregistrer les métadonnées de la séance : {exc}",
        ) from exc


def _mark_audio_outputs_stale(folder: Path, metadata: dict[str, Any]) -> None:
    # Keep generated artifacts but explicitly tell the UI they no longer reflect
    # the currently enabled audio set. Successful jobs clear each flag separately.
    mark_core_audio_outputs_stale(folder, metadata)


def _ensure_session_idle_for_audio_edit(folder: Path) -> None:
    with STATE_LOCK:
        active = [job for job in JOBS.values() if job.get("session_id") == folder.name
                  and job.get("state") in {"running", "stopping", "queued"}]
    if active:
        raise HTTPException(status_code=409, detail="Impossible de modifier une piste pendant l’enregistrement ou le traitement de cette séance.")


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, request: RenameSessionRequest) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        active_jobs = [job for job in JOBS.values() if job.get("session_id") == folder.name and job.get("state") in {"running", "stopping", "queued"}]
    if active_jobs:
        raise HTTPException(status_code=409, detail="Impossible de renommer une séance pendant son enregistrement ou son traitement.")
    try:
        return rename_core_session(PROJECT_ROOT, SESSION_ROOT, folder.name, request.title)
    except SessionServiceError as exc:
        message = str(exc)
        status = 422 if "titre" in message else 409 if "cours" in message or "active" in message else 500
        raise HTTPException(status_code=status, detail=message) from exc


@app.put("/api/sessions/{session_id}/settings")
def save_session_settings(session_id: str, request: SessionSettingsRequest) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        active = any(job.get("session_id") == folder.name and job.get("state") in {"queued", "running", "stopping"} for job in JOBS.values())
    if active:
        raise HTTPException(status_code=409, detail="Impossible de modifier les options pendant le traitement de cette séance.")
    request.settings.namespace(folder=str(folder))  # validate the shared settings contract before persistence
    value = _serialize_model(request.settings)
    try:
        result = save_core_processing_settings(PROJECT_ROOT, SESSION_ROOT, folder.name, value)
    except SessionServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": session_id, "settings": value, "metadata": result["metadata"]}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        active = [job for job in JOBS.values() if job.get("session_id") == folder.name and job.get("state") in {"running", "stopping", "queued"}]
    if active:
        raise HTTPException(status_code=409, detail="Impossible de supprimer une séance pendant son enregistrement ou son traitement.")
    try:
        return delete_core_session(PROJECT_ROOT, SESSION_ROOT, folder.name)
    except SessionServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/sessions/{session_id}/audio/{filename}")
def set_session_audio_track_disabled(session_id: str, filename: str, request: AudioTrackToggleRequest) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.lower().endswith(".wav"):
        raise HTTPException(status_code=404, detail="Piste audio inconnue.")
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    _ensure_session_idle_for_audio_edit(folder)
    try:
        return set_core_audio_track_disabled(PROJECT_ROOT, SESSION_ROOT, folder.name, filename, disabled=request.disabled)
    except SessionServiceError as exc:
        message = str(exc)
        status = 422 if "Au moins une piste" in message else 409 if "Impossible" in message else 404 if "introuvable" in message else 500
        raise HTTPException(status_code=status, detail=message) from exc


@app.delete("/api/sessions/{session_id}/audio/{filename}")
def delete_session_audio_track(session_id: str, filename: str) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.lower().endswith(".wav"):
        raise HTTPException(status_code=404, detail="Piste audio inconnue.")
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    _ensure_session_idle_for_audio_edit(folder)
    try:
        return delete_core_audio_track(PROJECT_ROOT, SESSION_ROOT, folder.name, filename)
    except SessionServiceError as exc:
        message = str(exc)
        status = 409 if "Impossible" in message else 404 if "introuvable" in message else 500
        raise HTTPException(status_code=status, detail=message) from exc


@app.get("/api/sessions/{session_id}/audio/{filename}")
def session_audio(session_id: str, filename: str, request: Request):
    """Stream an existing WAV track with HTTP Range support for native audio controls."""
    if Path(filename).name != filename or not filename.lower().endswith(".wav"):
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

    known_tracks = {path.name: path for path in list_audio_paths(folder)}
    path = known_tracks.get(filename)
    if path is None or not path.is_file():
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


@app.put("/api/sessions/{session_id}/summary")
def save_session_summary(session_id: str, request: SaveSummaryRequest) -> dict[str, Any]:
    """Save a user-edited summary through the same core operation as the CLI."""
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc
    with STATE_LOCK:
        active = [job for job in JOBS.values() if job.get("session_id") == folder.name and job.get("state") in {"queued", "running", "stopping"}]
        if active:
            raise HTTPException(status_code=409, detail="Le résumé ne peut pas être modifié pendant un traitement.")
        try:
            return save_core_summary(PROJECT_ROOT, SESSION_ROOT, folder.name, request.content, revision=request.revision)
        except SessionServiceError as exc:
            message = str(exc)
            status = 409 if "changé" in message or "cours" in message or "disponible" in message else 422 if "vide" in message or "taille" in message else 500
            raise HTTPException(status_code=status, detail=message) from exc


def _artifact_tail_hash(value: str) -> str:
    """Stable FNV-1a 32-bit hash over Unicode code points."""
    result = 2166136261
    for char in value:
        result ^= ord(char)
        result = (result * 16777619) & 0xFFFFFFFF
    return f"{result:08x}"


@app.get("/api/sessions/{session_id}/{kind}")
def session_artifact(session_id: str, kind: str, response: Response,
                     revision: str | None = None, offset: int = 0,
                     tail_hash: str | None = None, translation: str | None = None) -> dict[str, Any]:
    if kind not in {"summary", "transcript"}:
        raise HTTPException(status_code=404, detail="Document inconnu.")
    try:
        folder = resolve_session_folder(SESSION_ROOT, session_id)
        response.headers["Cache-Control"] = "no-store"
        if translation is not None and (kind != "summary" or translation not in TRANSLATION_LANGUAGE_CODES):
            raise HTTPException(status_code=422, detail="Langue de traduction invalide.")
        active_job = None if translation is not None else _active_session_artifact_job(session_id, kind)
        live_path = None if translation is not None else _live_session_artifact(folder, session_id, kind)
        if active_job and live_path is None:
            # Never fall back to the previous completed file while its replacement
            # is being prepared. Otherwise the detail pane can show stale content
            # until the first live chunk is written.
            return {
                "session_id": session_id,
                "kind": kind,
                "filename": "",
                "revision": f"pending:{active_job.get('id', '')}",
                "pending": True,
                "content": "",
                "live": False,
            }
        path = (summary_translation_path(folder, translation) if translation is not None else
                live_path or (summary_path(folder) if kind == "summary" else transcript_path(folder)))
        if path is None:
            raise FileNotFoundError(f"Aucun document {kind} trouvé pour cette séance.")
        stat = path.stat()
        current_revision = f"{stat.st_mtime_ns}:{stat.st_size}"
        is_live = live_path is not None
        result: dict[str, Any] = {
            "session_id": session_id,
            "kind": kind,
            "filename": path.name,
            "revision": current_revision,
            "live": is_live,
            "language": translation or "source",
        }
        if revision == current_revision:
            result["unchanged"] = True
            return result
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        offset = max(0, offset)
        if offset > 0 and offset <= len(content):
            if tail_hash is None:
                prefix_ok = True
            else:
                # The client sends a hash of the last code points it already
                # has; a mismatch means the content was rewritten.
                window = content[max(0, offset - ARTIFACT_TAIL_CODE_POINTS):offset]
                prefix_ok = _artifact_tail_hash(window) == tail_hash
            if prefix_ok:
                result["content"] = content[offset:]
                result["append"] = True
            else:
                result["content"] = content
                result["append"] = False
        else:
            result["content"] = content
            result["append"] = False
        result["unchanged"] = False
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs")
def jobs() -> dict[str, Any]:
    _initialize_persistence()
    with STATE_LOCK:
        return _jobs_response_locked()


@app.get("/api/events")
async def job_events(request: Request) -> StreamingResponse:
    """Stream current job snapshots and updates to the frontend over SSE."""
    await asyncio.to_thread(_initialize_persistence)
    loop = asyncio.get_running_loop()
    subscriber_id = uuid.uuid4().hex
    subscriber_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=128)
    # Register while holding the same lock order used by publishers so the
    # initial snapshot cannot race with a state change and leave a gap. Pending
    # events are flushed to existing subscribers before the registration, so the
    # new stream starts from a snapshot that is never older than its next event.
    with STATE_LOCK:
        with JOB_EVENT_LOCK:
            _flush_job_events_locked()
            initial = _jobs_response_locked()
            JOB_EVENT_SUBSCRIBERS[subscriber_id] = (loop, subscriber_queue)

    async def stream():
        try:
            yield "retry: 2000\n"
            yield f"event: snapshot\ndata: {json.dumps(initial, ensure_ascii=False, separators=(',', ':'))}\n\n"
            while not await request.is_disconnected():
                try:
                    event_name, data = await asyncio.wait_for(subscriber_queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event_name == JOB_EVENT_SHUTDOWN:
                    break
                yield f"event: {event_name}\ndata: {data}\n\n"
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Browsers may close an SSE connection while the ASGI response is
            # sending the next event. This is not a processing-job failure.
            return
        finally:
            with JOB_EVENT_LOCK:
                JOB_EVENT_SUBSCRIBERS.pop(subscriber_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


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
            CANCEL_EVENTS.pop(job_id, None)
            if JOB_STORE is not None:
                JOB_STORE.delete(job_id)
            deleted += 1
    if deleted:
        _publish_jobs_snapshot()
    return {"deleted": deleted}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel queued model work or request a cooperative stop for a running job."""
    _initialize_persistence()
    with STATE_LOCK:
        record = JOBS.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Tâche introuvable.")
        if record.get("state") not in {"queued", "running", "stopping"}:
            raise HTTPException(status_code=409, detail="Cette tâche est déjà terminée.")
        if record.get("kind") == "recording":
            stop_event = STOP_EVENTS.get(job_id)
            if record.get("phase") != "recording" or stop_event is None:
                raise HTTPException(status_code=409, detail="L’enregistrement est déjà en finalisation et ne peut plus être annulé.")
            stop_event.set()
            _transition_job_phase_locked(record, "finalizing")
            record.update({"state": "stopping", "phase": "finalizing", "message": "Arrêt demandé : finalisation des pistes WAV…", "updated_at": _now()})
            _persist_job_locked(record)
            return _job_public(record)

        cancel_event = CANCEL_EVENTS.get(job_id)
        if cancel_event is None:
            cancel_event = threading.Event()
            CANCEL_EVENTS[job_id] = cancel_event
        cancel_event.set()
        if record.get("state") == "queued":
            if job_id in PROCESSING_QUEUE_IDS:
                PROCESSING_QUEUE_IDS.remove(job_id)
            _transition_job_phase_locked(record, "cancelled")
            record.update({"state": "cancelled", "phase": "cancelled", "message": "Traitement annulé avant le démarrage.", "finished_at": _now(), "updated_at": _now(), "queue_position": None})
            _refresh_queue_positions_locked()
            CANCEL_EVENTS.pop(job_id, None)
        else:
            record.update({"state": "stopping", "message": "Annulation demandée · arrêt du traitement en cours…", "updated_at": _now()})
        _persist_job_locked(record)
        return _job_public(record)


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
        CANCEL_EVENTS.pop(job_id, None)
        if JOB_STORE is not None:
            JOB_STORE.delete(job_id)
    _publish_jobs_snapshot()
    return {"deleted": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    return _get_job_or_404(job_id)


@app.post("/api/jobs")
def start_session_job(request: JobRequest) -> dict[str, Any]:
    if request.action == "translate-summary" and request.settings.summary_language == "auto":
        raise HTTPException(status_code=422, detail="Choisissez une langue cible explicite pour traduire le résumé.")
    try:
        folder = resolve_session_folder(SESSION_ROOT, request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Séance introuvable.") from exc

    with STATE_LOCK:
        active = any(
            job.get("session_id") == folder.name
            and job.get("state") in {"queued", "running", "stopping"}
            for job in JOBS.values()
        )
    if active:
        raise HTTPException(status_code=409, detail="Un traitement est déjà en cours pour cette séance.")

    try:
        existing_metadata = read_core_metadata(folder)
    except SessionServiceError:
        # Keep the previous tolerant behavior: invalid metadata is replaced below.
        existing_metadata = {}
    if request.action != "translate-summary" and (
        not isinstance(existing_metadata, dict)
        or not isinstance(existing_metadata.get("processing_settings"), dict)
    ):
        _save_session_processing_settings(folder, request.settings)

    def worker(job_id: str) -> None:
        _run_session_job(request.action, folder, request.settings, job_id,
                         force=request.force)

    label = {"transcribe": "Transcription lancée", "summarize": "Résumé lancé", "process": "Traitement complet lancé", "translate-summary": "Traduction du résumé lancée"}[request.action]
    return _start_job(
        request.action, label, worker, session_id=folder.name,
        payload={"type": "session", "action": request.action, "session_id": folder.name,
                 "settings": _serialize_model(request.settings), "checkpoint": None},
    )


@app.post("/api/recording/start")
def start_recording(request: RecordRequest) -> dict[str, Any]:
    if request.settings.format not in VALID_FORMATS:
        raise HTTPException(status_code=422, detail="Format de résumé invalide.")
    if request.sources is not None:
        if not request.sources:
            raise HTTPException(status_code=422, detail="Ajoutez au moins une source audio avant de démarrer.")
        identities = [(source.kind, source.device_id or source.device_name.casefold()) for source in request.sources]
        if len(set(identities)) != len(identities):
            raise HTTPException(status_code=422, detail="Une même source audio ne peut pas être ajoutée deux fois.")
        request.capture_microphone = any(source.kind == "microphone" for source in request.sources)
        request.capture_windows = any(source.kind == "output" for source in request.sources)
    elif not request.capture_microphone and not request.capture_windows:
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
        elif (
            "finalisation des pistes wav" in folded
            or "pistes wav finalisées" in folded
            or "écriture de micro.wav" in folded
            or "écriture de windows.wav" in folded
        ):
            phase = "finalizing"
        elif any(term in folded for term in (
            "llm", "analyse", "génération du résumé", "résumé", "synthèse", "rédaction", "relecture",
        )):
            phase = "summarizing"
        elif "whisper" in folded or "transcription" in folded:
            phase = "transcribing"
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
        args.audio_sources = [source.model_dump() for source in request.sources] if request.sources is not None else None
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
                complete_recording_job_id=job_id,
            )
            final_message = f"Enregistrement terminé · traitement en file (position {queued.get('queue_position') or 1})"
        else:
            final_message = "Enregistrement terminé · pistes WAV disponibles"
        _set_job(
            job_id, session_id=folder.name if folder else None, state="completed",
            phase="completed", message=final_message, finished_at=_now(), queue_position=None,
        )

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
        _transition_job_phase_locked(JOBS[active["id"]], "finalizing")
        JOBS[active["id"]].update({"state": "stopping", "phase": "finalizing", "message": "Arrêt demandé : finalisation des pistes WAV…", "updated_at": _now()})
        _persist_job_locked(JOBS[active["id"]])
        return _job_public(JOBS[active["id"]])


@app.post("/api/import")
async def import_and_process(
    file: UploadFile = File(...),
    settings_json: str = Form("{}"),
    action: Literal["process", "transcribe"] = Form("process"),
    normalize_windows: bool = Form(True),
    normalize_windows_max_gain_db: float = Form(30.0),
) -> dict[str, Any]:
    try:
        raw_settings = json.loads(settings_json)
        settings = Settings(**raw_settings)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Paramètres d'importation invalides : {exc}") from exc
    if not 0.0 <= normalize_windows_max_gain_db <= 30.0:
        raise HTTPException(status_code=422, detail="Le gain maximal de normalisation doit être compris entre 0 et 30 dB.")
    media_info = get_provider_info(settings.media_provider)
    if media_info is None or media_info.task != "media":
        raise HTTPException(status_code=422, detail="Provider média inconnu.")
    media_options = dict(settings.provider_options.get(settings.media_provider) or {})
    if settings.media_provider == DEFAULT_MEDIA_PROVIDER:
        # Historical top-level settings remain aliases for the ffmpeg provider options.
        media_options.setdefault("ffmpeg", _program_path(settings.ffmpeg))
        media_options.setdefault("ffprobe", _program_path(settings.ffprobe))
    try:
        ensure_media_toolchain_ready(media_info, media_options, PROJECT_ROOT)
    except MediaToolchainUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
                    raise HTTPException(status_code=413, detail="Fichier trop volumineux (limite : 5 Go).")
                await asyncio.to_thread(target.write, chunk)
    except BaseException:
        # No job owns this temporary file yet, so never leave it behind.
        if file_path is not None:
            file_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if file_path is None or total == 0:
        if file_path:
            file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Fichier vide ou non reçu.")
    display_name = Path(file.filename or "fichier audio").name

    job_payload = {
        "type": "import", "action": action, "source_file": str(file_path),
        "display_name": display_name,
        "settings": _serialize_model(settings),
        "normalization": {
            "enabled": normalize_windows,
            "max_gain_db": normalize_windows_max_gain_db,
        },
    }
    try:
        return _enqueue_job(
            "import", f"Import de {display_name} en préparation",
            _run_import_job, payload=job_payload,
        )
    except BaseException:
        # The queue rejected the job: its source file is still unowned.
        file_path.unlink(missing_ok=True)
        raise


def _decorate_search_sources(
    sources: list[dict[str, Any]], included_source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Attach stable source IDs and citation numbers without changing source identity."""
    decorated: list[dict[str, Any]] = []
    citation_number = 0
    for source in sources:
        item = dict(source)
        source_id = str(item.get("source_id") or item.get("source_number") or len(decorated) + 1)
        included = included_source_ids is None or source_id in included_source_ids
        item["source_id"] = source_id
        item["included"] = included
        if included:
            citation_number += 1
            item["citation_number"] = citation_number
        else:
            item["citation_number"] = None
        decorated.append(item)
    return decorated


def _search_public(search: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in search.items() if not key.startswith("_")}


def _set_search(search_id: str, **updates: Any) -> None:
    public: dict[str, Any] | None = None
    with SEARCH_LOCK:
        if search_id in SEARCHES:
            SEARCHES[search_id].update(updates)
            SEARCHES[search_id]["updated_at"] = _now()
            public = _search_public(SEARCHES[search_id])
    if public is not None:
        with JOB_EVENT_LOCK:
            _coalesce_job_event_locked("search", public, f"search:{search_id}")


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
    """Search-synthesis application adapter around the framework-independent core."""
    profiled_settings = Settings(**apply_processing_profile(
        settings.model_dump() if hasattr(settings, "model_dump") else settings.dict()
    ))
    return _generate_search_synthesis_impl(
        query, passages, profiled_settings, binary, model,
        cancel_event=cancel_event, on_process=on_process, on_progress=on_progress,
        working_directory=PROJECT_ROOT, provider_id=profiled_settings.text_provider,
        completion_runner=run_completion_resilient,
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
                sources=_decorate_search_sources(items),
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
            session_ids=set(request.session_ids) if request.session_ids else None,
        )
        with SEARCH_LOCK:
            latest = SEARCHES.get(search_id, {})
            progress_snapshot = {
                "sessions_scanned": latest.get("sessions_scanned", 0),
                "sessions_total": latest.get("sessions_total", 0),
                "passages_found": latest.get("passages_found", len(passages)),
            }
        passages = _decorate_search_sources(passages)
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
        except (LLMError, ValueError) as exc:
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
            "session_ids": list(request.session_ids),
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
            "_settings": request.settings,
        }
        SEARCHES[search_id] = search
        SEARCH_CANCEL_EVENTS[search_id] = threading.Event()
        ACTIVE_SEARCH_ID = search_id
        public = _search_public(search)
    with JOB_EVENT_LOCK:
        _coalesce_job_event_locked("search", public, f"search:{search_id}")
    threading.Thread(
        target=_run_cancellable_search,
        args=(search_id, request),
        name=f"glimio-web-search-{search_id}",
        daemon=True,
    ).start()
    return _search_public(search)


def _run_search_resynthesis(search_id: str, passages: list[dict[str, Any]], settings: Settings) -> None:
    """Regenerate only the final synthesis from user-confirmed source selections."""
    cancel_event = SEARCH_CANCEL_EVENTS[search_id]
    try:
        binary = Path(settings.llama_completion).expanduser()
        model = Path(settings.gguf).expanduser()
        if not binary.is_absolute():
            binary = PROJECT_ROOT / binary
        if not model.is_absolute():
            model = PROJECT_ROOT / model

        def publish_process(active_process: subprocess.Popen[Any] | None) -> None:
            with SEARCH_LOCK:
                if search_id in SEARCHES:
                    if active_process is None:
                        SEARCHES[search_id].pop("_process", None)
                    else:
                        SEARCHES[search_id]["_process"] = active_process

        def publish_progress(message: str) -> None:
            if not cancel_event.is_set():
                _set_search(search_id, message=message)

        answer, hit_limit = _generate_search_synthesis(
            str(SEARCHES[search_id].get("query", "")), passages, settings, binary, model,
            cancel_event=cancel_event, on_process=publish_process, on_progress=publish_progress,
        )
        if cancel_event.is_set():
            _finish_search_cancelled(search_id)
            return
        if hit_limit:
            _set_search(search_id, state="error", message="Synthèse tronquée", answer=None,
                        llm_error="Le modèle a atteint sa limite de génération sans terminer sa réponse.", finished_at=_now())
            return
        if _looks_like_malformed_synthesis(answer):
            _set_search(search_id, state="error", message="Synthèse locale de mauvaise qualité", answer=None,
                        llm_error="Le modèle a renvoyé une sortie de raisonnement interne ou répétitive. Vérifie que le modèle est adapté à la rédaction.", finished_at=_now())
            return
        if _has_unknown_citations(answer, passages):
            _set_search(search_id, state="error", message="Références de synthèse invalides", answer=None,
                        llm_error="La synthèse cite des sources absentes des extraits conservés. Elle n’a pas été affichée pour éviter des références trompeuses.", finished_at=_now())
            return
        _set_search(search_id, state="completed", message="Synthèse actualisée", answer=answer, llm_error=None, finished_at=_now())
    except LLMCancelled:
        _finish_search_cancelled(search_id)
    except (LLMError, ValueError) as exc:
        if cancel_event.is_set():
            _finish_search_cancelled(search_id)
        else:
            _set_search(search_id, state="error", message="Échec de la génération locale", answer=None,
                        llm_error=str(exc), finished_at=_now())
    except (Exception, SystemExit) as exc:
        if cancel_event.is_set():
            _finish_search_cancelled(search_id)
        else:
            _set_search(search_id, state="error", message="La synthèse n’a pas pu être actualisée", answer=None,
                        llm_error=str(exc).strip() or f"Erreur pendant la synthèse ({type(exc).__name__}).", finished_at=_now())
    finally:
        global ACTIVE_SEARCH_ID
        with SEARCH_LOCK:
            if search_id in SEARCHES:
                SEARCHES[search_id].pop("_process", None)
            SEARCH_CANCEL_EVENTS.pop(search_id, None)
            if ACTIVE_SEARCH_ID == search_id:
                ACTIVE_SEARCH_ID = None


@app.post("/api/search/{search_id}/synthesize")
def synthesize_library_search(search_id: str, request: SearchSynthesisRequest) -> dict[str, Any]:
    """Start one synthesis pass after the user confirms the kept excerpts."""
    global ACTIVE_SEARCH_ID
    with SEARCH_LOCK:
        search = SEARCHES.get(search_id)
        if search is None:
            raise HTTPException(status_code=404, detail="Recherche inconnue ou historique expiré.")
        if ACTIVE_SEARCH_ID and ACTIVE_SEARCH_ID in SEARCHES and SEARCHES[ACTIVE_SEARCH_ID].get("state") in {"running", "cancelling"}:
            raise HTTPException(status_code=409, detail="Une recherche IA est déjà en cours.")
        current_sources = search.get("sources", [])
        source_ids = {str(item.get("source_id") or item.get("source_number")) for item in current_sources}
        requested_ids = set(request.source_ids)
        if not requested_ids or not requested_ids.issubset(source_ids):
            raise HTTPException(status_code=422, detail="La sélection des extraits est invalide. Relancez la recherche.")
        selected = [dict(item) for item in current_sources if str(item.get("source_id") or item.get("source_number")) in requested_ids]
        for citation_number, passage in enumerate(selected, start=1):
            passage["source_number"] = citation_number
        settings = search.get("_settings")
        if settings is None:
            raise HTTPException(status_code=409, detail="Les paramètres de cette recherche ne sont plus disponibles. Relancez-la.")
        decorated = _decorate_search_sources(current_sources, requested_ids)
        search.update({
            "sources": decorated,
            "state": "running",
            "message": "Actualisation de la synthèse à partir des extraits conservés…",
            "answer": None,
            "llm_error": None,
            "finished_at": None,
            "updated_at": _now(),
        })
        SEARCH_CANCEL_EVENTS[search_id] = threading.Event()
        ACTIVE_SEARCH_ID = search_id
        public = _search_public(search)
    with JOB_EVENT_LOCK:
        _coalesce_job_event_locked("search", public, f"search:{search_id}")
    threading.Thread(
        target=_run_search_resynthesis,
        args=(search_id, selected, settings),
        name=f"glimio-web-search-synthesis-{search_id}",
        daemon=True,
    ).start()
    return public


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
    with JOB_EVENT_LOCK:
        _coalesce_job_event_locked("search", public, f"search:{search_id}")
    if process is not None:
        try:
            if process.poll() is None:
                process.terminate()
        except OSError:
            pass
    return public


@app.post("/api/search/ask")
def ask_library(request: SearchRequest) -> dict[str, Any]:
    passages = retrieve_passages(
        SESSION_ROOT, request.query, request.top_k,
        session_ids=set(request.session_ids) if request.session_ids else None,
    )
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


# Catch-all SPA route — MUST be registered last (after every /api/* endpoint)
# so Starlette keeps API priority and only unmatched paths fall back to the
# Angular index.html. Serves hashed assets (main-*.js, styles-*.css, brand/…).
app.add_api_route("/{spa_path:path}", angular_spa, methods=["GET"], include_in_schema=False)


def main() -> None:
    # Required by the spawn-based diarization child in frozen (PyInstaller) builds.
    mp.freeze_support()
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
        if not getattr(sys, "frozen", False) and (
            os.environ.get("GLIMIO_WEB_BUILD", "").casefold() in {"1", "true", "yes"}
            or _sources_newer_than_build()
        ):
            _install_frontend_dependencies()
            _build_frontend()
    except SystemExit as exc:
        print(f"[web] {exc}", flush=True)
        raise
    global ANGULAR_DIST_DIR
    ANGULAR_DIST_DIR = _ensure_angular_dist()

    # Create the SQLite database (and its schema) up front so every /api/*
    # route works out of the box on a fresh clone, without a manual step.
    _warmup_persistence()

    url = f"http://{host}:{port}"
    print(f"Glimio Web : {url}", flush=True)
    print(f"Racine du projet : {PROJECT_ROOT}", flush=True)
    print(f"Dossier des séances : {SESSION_ROOT} (existe : {SESSION_ROOT.is_dir()})", flush=True)
    if os.environ.get("GLIMIO_WEB_OPEN_BROWSER", os.environ.get("SEANCE_WEB_OPEN_BROWSER", "1")).casefold() not in {"0", "false", "no"}:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    class GlimioUvicornServer(uvicorn.Server):
        async def shutdown(self, sockets=None) -> None:
            # Uvicorn otherwise waits forever for long-lived SSE connections before
            # it sends the ASGI lifespan shutdown event.
            _close_job_event_streams()
            await super().shutdown(sockets)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        timeout_graceful_shutdown=10,
    )
    try:
        GlimioUvicornServer(config).run()
    except KeyboardInterrupt:
        # Uvicorn re-raises the captured SIGINT after its graceful shutdown.
        # Treat the user's Ctrl+C as a normal exit instead of printing a traceback.
        pass
