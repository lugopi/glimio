"""Stable, UI-neutral provider information and progress contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Literal, Protocol


ProviderTask = Literal["transcription", "generation", "diarization", "media"]
ProviderEventCallback = Callable[["ProviderEvent"], None]


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Provider-independent inputs for one text-generation operation."""

    system_prompt: str
    user_prompt: str
    context_tokens: int
    max_output_tokens: int
    temperature: float = 0.2
    stage: str = "Génération"
    retries: int = 2


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    hit_token_limit: bool = False


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    audio_path: str
    model_path: str
    output_prefix: str
    language: str = "auto"
    threads: int = 1


class TextGenerationProvider(Protocol):
    """Adapter contract consumed by summarization and search use cases."""

    info: ProviderInfo

    def generate(
        self,
        request: GenerationRequest,
        *,
        on_event: ProviderEventCallback | None = None,
    ) -> GenerationResult: ...

    def generate_once(self, request: GenerationRequest) -> GenerationResult: ...


class TranscriptionProvider(Protocol):
    """Adapter contract; results use Glimio timestamps rather than vendor formats."""

    info: ProviderInfo

    def transcribe(
        self,
        request: TranscriptionRequest,
        *,
        on_event: ProviderEventCallback | None = None,
    ) -> list[TranscriptSegment]: ...


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """Static identity and capability information exposed by a provider."""

    id: str
    name: str
    task: ProviderTask
    description: str
    execution: Literal["embedded", "bundled_executable", "system_executable", "remote"]
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Current readiness information safe for the CLI or a UI to display."""

    provider: ProviderInfo
    ready: bool
    message: str
    version: str | None = None
    missing: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.provider.id,
            "name": self.provider.name,
            "task": self.provider.task,
            "description": self.provider.description,
            "execution": self.provider.execution,
            "capabilities": list(self.provider.capabilities),
            "ready": self.ready,
            "message": self.message,
            "version": self.version,
            "missing": list(self.missing),
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    """Structured progress emitted by providers, independent of any UI framework."""

    provider_id: str
    task: ProviderTask
    stage: str
    message: str
    progress: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "task": self.task,
            "stage": self.stage,
            "message": self.message,
            "progress": self.progress,
            "details": dict(self.details),
        }
