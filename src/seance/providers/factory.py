"""Provider construction point used by use cases and application adapters."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Mapping

from .llama_cpp import LlamaCppTextProvider
from .whisper_cpp import WhisperCppTranscriptionProvider
from .contracts import TextGenerationProvider, TranscriptionProvider


DEFAULT_TEXT_PROVIDER = "llama.cpp"
DEFAULT_TRANSCRIPTION_PROVIDER = "whisper.cpp"

_TEXT_PROVIDER_FACTORIES = {DEFAULT_TEXT_PROVIDER: LlamaCppTextProvider}
_TRANSCRIPTION_PROVIDER_FACTORIES = {DEFAULT_TRANSCRIPTION_PROVIDER: WhisperCppTranscriptionProvider}
TEXT_PROVIDER_IDS = tuple(_TEXT_PROVIDER_FACTORIES)
TRANSCRIPTION_PROVIDER_IDS = tuple(_TRANSCRIPTION_PROVIDER_FACTORIES)


def registered_provider_infos():
    """Return the UI-neutral metadata declared by all active provider adapters."""
    factories = (*_TEXT_PROVIDER_FACTORIES.values(), *_TRANSCRIPTION_PROVIDER_FACTORIES.values())
    return tuple(factory.info for factory in factories)


def create_text_provider(
    provider_id: str,
    executable: str | Path,
    model: str | Path,
    working_directory: str | Path,
    *,
    cancel_event: Event | None = None,
    on_process: Any = None,
    timeout_seconds: float | None = None,
    completion_runner: Any = None,
    options: Mapping[str, Any] | None = None,
) -> TextGenerationProvider:
    """Construct a generation adapter; add new engines here, not in use cases."""
    if options is None:
        from .selection import selected_text_provider_options
        options = selected_text_provider_options()
    try:
        provider_factory = _TEXT_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de génération inconnu : {provider_id}") from exc
    constructor_options: dict[str, Any] = {}
    if provider_id == DEFAULT_TEXT_PROVIDER and completion_runner is not None:
        constructor_options["completion_runner"] = completion_runner
    return provider_factory(
        executable, model, working_directory, cancel_event=cancel_event,
        on_process=on_process, timeout_seconds=timeout_seconds,
        options=dict(options or {}), **constructor_options,
    )


def create_transcription_provider(
    provider_id: str,
    executable: str | Path,
    *,
    cancel_event: Event | None = None,
    openvino_device: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> TranscriptionProvider:
    """Construct a speech adapter; add new engines here, not in orchestration."""
    try:
        provider_factory = _TRANSCRIPTION_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de transcription inconnu : {provider_id}") from exc
    return provider_factory(
        executable, cancel_event=cancel_event, openvino_device=openvino_device,
        openvino_enabled=bool((options or {}).get("openvino_enabled", False)),
        options=dict(options or {}),
    )
