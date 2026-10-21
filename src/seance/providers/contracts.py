"""Stable, UI-neutral provider information and progress contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Literal, Protocol


ProviderTask = Literal["transcription", "generation", "diarization", "media"]
ProviderOptionType = Literal["text", "path", "secret", "number", "boolean", "select"]
ProviderEventCallback = Callable[["ProviderEvent"], None]


@dataclass(frozen=True, slots=True)
class ProviderOptionChoice:
    value: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True, slots=True)
class ProviderOption:
    """UI-neutral configuration field declared by a provider adapter."""

    key: str
    label: str
    type: ProviderOptionType
    default: Any = None
    description: str = ""
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[ProviderOptionChoice, ...] = ()
    advanced: bool = False
    per_job: bool = False
    depends_on: str | None = None
    depends_value: Any = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "description": self.description,
            "required": self.required,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "choices": [choice.to_dict() for choice in self.choices],
            "advanced": self.advanced,
            "per_job": self.per_job,
            "depends_on": self.depends_on,
            "depends_value": self.depends_value,
        }


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
    options: tuple[ProviderOption, ...] = ()


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
            "options": [option.to_dict() for option in self.provider.options],
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
