"""Stable, UI-neutral provider information and progress contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Literal, Protocol


ProviderTask = Literal["transcription", "generation", "diarization", "media", "enhancement", "separation", "speaker_embedding"]
ProviderOptionType = Literal["text", "path", "secret", "number", "boolean", "select"]
ProviderResourceKind = Literal["documentation", "binary", "model", "package", "license"]
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


@dataclass(frozen=True, slots=True)
class AudioEnhancementRequest:
    """Inputs for an optional audio-enhancement provider."""

    audio_path: str
    output_path: str
    ffmpeg: str = "ffmpeg"
    cancel_event: Any = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AudioEnhancementResult:
    audio_path: str
    provider_id: str
    changed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AudioSeparationRequest:
    """Inputs for a source-separation provider. Outputs are independent audio stems."""

    audio_path: str
    output_directory: str
    output_prefix: str
    ffmpeg: str = "ffmpeg"
    cancel_event: Any = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AudioSeparationResult:
    audio_paths: tuple[str, ...]
    provider_id: str
    details: dict[str, Any] = field(default_factory=dict)
    # Stable global identity for each output source, aligned with ``audio_paths``.
    # ``None`` means that the chunk has no confidently detectable voice in this stem.
    source_ids: tuple[str | None, ...] = ()


class SpeakerEmbeddingProvider(Protocol):
    info: ProviderInfo

    def embed(self, audio: Any, sample_rate: int) -> Any: ...


class AudioEnhancementProvider(Protocol):
    info: ProviderInfo

    def enhance(self, request: AudioEnhancementRequest) -> AudioEnhancementResult: ...


class AudioSeparationProvider(Protocol):
    info: ProviderInfo

    def separate(self, request: AudioSeparationRequest) -> AudioSeparationResult: ...


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
class ProviderResourceLink:
    """Curated setup resource (documentation, binary, model, package, or license)."""

    label: str
    url: str
    kind: ProviderResourceKind = "documentation"
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "url": self.url, "kind": self.kind, "description": self.description}


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """Static identity, capabilities, dependencies, and setup guidance for a provider."""

    id: str
    name: str
    task: ProviderTask
    description: str
    execution: Literal["embedded", "bundled_executable", "system_executable", "remote"]
    capabilities: tuple[str, ...] = ()
    options: tuple[ProviderOption, ...] = ()
    # Hard provider-to-provider requirements (e.g. SepFormer requires ECAPA).
    requires: tuple[str, ...] = ()
    # Installer data is declarative; runtime code only executes metadata from this
    # trusted built-in catalog, never package names supplied by an HTTP request.
    python_install_extra: str | None = None
    python_install_packages: tuple[str, ...] = ()
    python_install_note: str = ""
    restart_after_python_install: bool = True
    setup_links: tuple[ProviderResourceLink, ...] = ()
    # Provider-owned UI translations keyed by locale, then by the exact source text.
    # This keeps optional integrations self-contained instead of extending the app-wide dictionary.
    translations: dict[str, dict[str, str]] = field(default_factory=dict)


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
            "requires": list(self.provider.requires),
            "python_install_extra": self.provider.python_install_extra,
            "python_install_packages": list(self.provider.python_install_packages),
            "python_install_note": self.provider.python_install_note,
            "restart_after_python_install": self.provider.restart_after_python_install,
            "python_install_available": bool(self.provider.python_install_extra or self.provider.python_install_packages),
            "setup_links": [link.to_dict() for link in self.provider.setup_links],
            "translations": {locale: dict(entries) for locale, entries in self.provider.translations.items()},
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
