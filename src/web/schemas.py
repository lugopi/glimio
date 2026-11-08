"""Typed REST response contracts for the FastAPI adapter.

The application core deliberately returns framework-independent dictionaries.
These DTOs validate the public boundary while allowing forward-compatible
provider metadata and session metadata to carry extension fields.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiResponseModel(BaseModel):
    """Common response model: validate known fields, preserve extensions."""

    model_config = ConfigDict(extra="allow")


class HealthResponse(ApiResponseModel):
    ok: bool
    project_root: str
    session_root: str
    session_root_exists: bool
    offline_local_mode: bool


class PreferencesResponse(ApiResponseModel):
    settings: dict[str, Any]
    ui: dict[str, Any]


class AppConfigResponse(ApiResponseModel):
    session_root: str
    session_root_exists: bool
    project_root: str
    processing_mode: str
    offline_local_mode: bool
    defaults: dict[str, Any]
    preferences: PreferencesResponse
    formats: list[str]
    processing_profiles: dict[str, dict[str, Any]]


class ProviderOptionChoiceResponse(ApiResponseModel):
    value: str
    label: str


class ProviderOptionResponse(ApiResponseModel):
    key: str
    label: str
    type: Literal["text", "path", "secret", "number", "boolean", "select"]
    default: Any = None
    description: str = ""
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: list[ProviderOptionChoiceResponse] = Field(default_factory=list)
    advanced: bool = False
    per_job: bool = False
    depends_on: str | None = None
    depends_value: Any = True
    path_role: Literal["asset", "executable"] = "asset"


class ProviderSetupLinkResponse(ApiResponseModel):
    label: str
    url: str
    kind: Literal["documentation", "binary", "model", "package", "license"]
    description: str = ""


class ProviderStatusResponse(ApiResponseModel):
    id: str
    name: str
    task: Literal["transcription", "generation", "diarization", "media", "enhancement", "separation", "speaker_embedding"]
    description: str
    translations: dict[str, dict[str, str]] = Field(default_factory=dict)
    execution: Literal["embedded", "bundled_executable", "system_executable", "remote"]
    capabilities: list[str] = Field(default_factory=list)
    options: list[ProviderOptionResponse] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    python_install_extra: str | None = None
    python_install_packages: list[str] = Field(default_factory=list)
    python_install_note: str = ""
    restart_after_python_install: bool = True
    python_install_available: bool = False
    python_install_runtime_available: bool = False
    python_install_block_reason: str = ""
    setup_links: list[ProviderSetupLinkResponse] = Field(default_factory=list)
    ready: bool
    message: str
    version: str | None = None
    missing: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ProvidersResponse(ApiResponseModel):
    providers: list[ProviderStatusResponse]


class ProviderInstallStatusResponse(ApiResponseModel):
    id: str
    provider_id: str
    state: Literal["queued", "running", "succeeded", "failed"]
    message: str
    output: str
    returncode: int | None = None
    restart_required: bool
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class ProviderInstallResponse(ApiResponseModel):
    install: ProviderInstallStatusResponse


class AudioDeviceInfoResponse(ApiResponseModel):
    id: str
    name: str
    key: str


class AudioDevicesResponse(ApiResponseModel):
    """Legacy display-name lists and stable endpoint records exposed by /api/devices."""

    microphones: list[str]
    outputs: list[str]
    microphone_devices: list[AudioDeviceInfoResponse]
    output_devices: list[AudioDeviceInfoResponse]


class ProcessingPhaseDurationResponse(ApiResponseModel):
    phase: str
    duration_seconds: float = Field(ge=0)


class SessionProcessingResponse(ApiResponseModel):
    job_id: str
    kind: str
    state: Literal["queued", "running", "stopping", "completed", "cancelled", "error"]
    phase: str
    active: bool
    message: str
    error: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    phase_started_at: str | None = None
    phase_history: list[ProcessingPhaseDurationResponse] = Field(default_factory=list)


class SessionSummaryResponse(ApiResponseModel):
    id: str
    title: str
    started_at: str | None = None
    summary_excerpt: str = ""
    summary: bool
    transcript: bool
    audio: bool
    audio_tracks: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    has_metadata: bool = False
    processing: SessionProcessingResponse | None = None


class SessionPageResponse(ApiResponseModel):
    items: list[SessionSummaryResponse]
    count: int
    page_count: int
    limit: int | Literal["all"]
    offset: int = Field(ge=0)
    root: str
    root_exists: bool
    project_root: str


class SessionFilesResponse(ApiResponseModel):
    summary: bool
    transcript: bool
    audio_tracks: list[str]
    analysis: bool


class AudioTrackDetailResponse(ApiResponseModel):
    filename: str
    disabled: bool
    path: str


class SessionDetailResponse(SessionSummaryResponse):
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary_translations: list[str] = Field(default_factory=list)
    files: SessionFilesResponse
    processing_settings: dict[str, Any] = Field(default_factory=dict)
    audio_tracks_detail: list[AudioTrackDetailResponse] = Field(default_factory=list)


class SessionArtifactResponse(ApiResponseModel):
    session_id: str
    kind: Literal["summary", "transcript"]
    language: str = "source"
    filename: str
    revision: str
    unchanged: bool = False
    pending: bool = False
    append: bool = False
    live: bool = False
    content: str | None = None


class SessionMutationResponse(ApiResponseModel):
    id: str
    title: str | None = None
    filename: str | None = None
    settings: dict[str, Any] | None = None
    audio_tracks: list[str] | None = None
    disabled_audio_tracks: list[str] | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionDeleteResponse(ApiResponseModel):
    deleted: bool
    id: str


class DeletedJobResponse(ApiResponseModel):
    deleted: str


class ClearJobHistoryResponse(ApiResponseModel):
    deleted: int = Field(ge=0)


class ProviderEventResponse(ApiResponseModel):
    provider_id: str
    task: Literal["transcription", "generation", "diarization", "media", "enhancement", "separation", "speaker_embedding"]
    stage: str
    message: str
    progress: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class JobResponse(ApiResponseModel):
    id: str
    kind: str
    state: Literal["queued", "running", "stopping", "completed", "cancelled", "error"]
    phase: str
    message: str = ""
    error: str | None = None
    session_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    phase_started_at: str | None = None
    phase_history: list[ProcessingPhaseDurationResponse] = Field(default_factory=list)
    queue_position: int | None = None
    provider_event: ProviderEventResponse | None = None


class JobQueueResponse(ApiResponseModel):
    waiting: int = Field(ge=0)
    running: JobResponse | None = None
    serial: bool


class JobsResponse(ApiResponseModel):
    items: list[JobResponse]
    active: JobResponse | None = None
    queue: JobQueueResponse


class SearchSourceResponse(ApiResponseModel):
    source_number: int | str
    source_id: str | None = None
    included: bool = True
    citation_number: int | None = None
    title: str
    session_id: str
    filename: str
    kind: str
    text: str


class SearchResultResponse(ApiResponseModel):
    id: str
    state: Literal["queued", "running", "cancelling", "completed", "cancelled", "error"]
    message: str = ""
    query: str
    session_ids: list[str] = Field(default_factory=list)
    sessions_total: int = Field(default=0, ge=0)
    sessions_scanned: int = Field(default=0, ge=0)
    passages_found: int = Field(default=0, ge=0)
    answer: str | None = None
    llm_error: str | None = None
    sources: list[SearchSourceResponse] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None


class SearchAskResponse(ApiResponseModel):
    query: str
    answer: str | None = None
    sources: list[SearchSourceResponse] = Field(default_factory=list)
    llm_error: str | None = None
