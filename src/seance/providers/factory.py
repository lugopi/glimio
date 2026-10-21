"""Provider construction point used by use cases and application adapters."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any

from .llama_cpp import LlamaCppTextProvider
from .whisper_cpp import WhisperCppTranscriptionProvider
from .contracts import TextGenerationProvider, TranscriptionProvider


DEFAULT_TEXT_PROVIDER = "llama.cpp"
DEFAULT_TRANSCRIPTION_PROVIDER = "whisper.cpp"

_TEXT_PROVIDER_FACTORIES = {DEFAULT_TEXT_PROVIDER: LlamaCppTextProvider}
_TRANSCRIPTION_PROVIDER_FACTORIES = {DEFAULT_TRANSCRIPTION_PROVIDER: WhisperCppTranscriptionProvider}
TEXT_PROVIDER_IDS = tuple(_TEXT_PROVIDER_FACTORIES)
TRANSCRIPTION_PROVIDER_IDS = tuple(_TRANSCRIPTION_PROVIDER_FACTORIES)


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
) -> TextGenerationProvider:
    """Construct a generation adapter; add new engines here, not in use cases."""
    try:
        provider_factory = _TEXT_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de génération inconnu : {provider_id}") from exc
    options = {}
    if provider_id == DEFAULT_TEXT_PROVIDER and completion_runner is not None:
        options["completion_runner"] = completion_runner
    return provider_factory(
        executable, model, working_directory, cancel_event=cancel_event,
        on_process=on_process, timeout_seconds=timeout_seconds, **options,
    )


def create_transcription_provider(
    provider_id: str,
    executable: str | Path,
    *,
    cancel_event: Event | None = None,
    openvino_device: str | None = None,
) -> TranscriptionProvider:
    """Construct a speech adapter; add new engines here, not in orchestration."""
    try:
        provider_factory = _TRANSCRIPTION_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de transcription inconnu : {provider_id}") from exc
    return provider_factory(
        executable, cancel_event=cancel_event, openvino_device=openvino_device,
    )
