"""Provider construction point used by use cases and application adapters."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Mapping

from .llama_cpp import LlamaCppTextProvider
from .whisper_cpp import WhisperCppTranscriptionProvider
from .sherpa_onnx import SHERPA_ONNX_INFO, SherpaOnnxDiarizationProvider
from .contracts import (
    SpeakerDiarizationProvider, TextGenerationProvider, TranscriptionProvider,
)
from .audio_processing import (
    EMBEDDING_PROVIDER_FACTORIES, ENHANCEMENT_PROVIDER_FACTORIES,
    SEPARATION_PROVIDER_FACTORIES, audio_processing_provider_infos,
)
from .media_tools import MEDIA_PROVIDER_FACTORIES, media_toolchain_provider_infos
from .plugins import plugins_for_task

DEFAULT_TEXT_PROVIDER = "llama.cpp"
DEFAULT_TRANSCRIPTION_PROVIDER = "whisper.cpp"
DEFAULT_DIARIZATION_PROVIDER = "sherpa-onnx"

_BUILTIN_TEXT_PROVIDER_FACTORIES = {DEFAULT_TEXT_PROVIDER: LlamaCppTextProvider}
_BUILTIN_TRANSCRIPTION_PROVIDER_FACTORIES = {DEFAULT_TRANSCRIPTION_PROVIDER: WhisperCppTranscriptionProvider}
_BUILTIN_DIARIZATION_PROVIDER_FACTORIES = {DEFAULT_DIARIZATION_PROVIDER: SherpaOnnxDiarizationProvider}

_TEXT_PROVIDER_FACTORIES = {
    **_BUILTIN_TEXT_PROVIDER_FACTORIES,
    **{p.info.id: p.factory for p in plugins_for_task("generation") if p.info.id not in _BUILTIN_TEXT_PROVIDER_FACTORIES},
}
_TRANSCRIPTION_PROVIDER_FACTORIES = {
    **_BUILTIN_TRANSCRIPTION_PROVIDER_FACTORIES,
    **{p.info.id: p.factory for p in plugins_for_task("transcription") if p.info.id not in _BUILTIN_TRANSCRIPTION_PROVIDER_FACTORIES},
}
_DIARIZATION_PROVIDER_FACTORIES = {
    **_BUILTIN_DIARIZATION_PROVIDER_FACTORIES,
    **{p.info.id: p.factory for p in plugins_for_task("diarization") if p.info.id not in _BUILTIN_DIARIZATION_PROVIDER_FACTORIES},
}

TEXT_PROVIDER_IDS = tuple(_TEXT_PROVIDER_FACTORIES)
TRANSCRIPTION_PROVIDER_IDS = tuple(_TRANSCRIPTION_PROVIDER_FACTORIES)
DIARIZATION_PROVIDER_IDS = tuple(_DIARIZATION_PROVIDER_FACTORIES)


def registered_provider_infos():
    """Return all active provider metadata in deterministic order, without duplicates."""
    # Add every built-in before any third-party metadata so a plugin cannot
    # shadow a core provider ID, regardless of its declared task.
    infos = (
        LlamaCppTextProvider.info,
        WhisperCppTranscriptionProvider.info,
        SHERPA_ONNX_INFO,
        *audio_processing_provider_infos(),
        *media_toolchain_provider_infos(),
        *(plugin.info for task in ("generation", "transcription", "diarization")
          for plugin in plugins_for_task(task)),
    )
    unique: dict[str, Any] = {}
    for info in infos:
        unique.setdefault(info.id, info)
    return tuple(unique.values())


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
    """Construct a generation adapter; installed providers use the same contract."""
    if options is None:
        from .selection import selected_text_provider_options
        options = selected_text_provider_options()
    try:
        provider_factory = _TEXT_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de génération inconnu : {provider_id}") from exc
    constructor_options: dict[str, Any] = {}
    # The optional testing/embedding runner belongs to llama.cpp; third-party
    # provider constructors need not implement an implementation-specific hook.
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
    options: Mapping[str, Any] | None = None,
) -> TranscriptionProvider:
    """Construct a transcription adapter without importing its engine eagerly."""
    try:
        provider_factory = _TRANSCRIPTION_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de transcription inconnu : {provider_id}") from exc
    return provider_factory(executable, cancel_event=cancel_event, options=dict(options or {}))


def create_speaker_diarization_provider(
    provider_id: str,
    options: Mapping[str, Any] | None = None,
) -> SpeakerDiarizationProvider:
    """Construct a speaker-turn detection engine behind the shared contract."""
    try:
        provider_factory = _DIARIZATION_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider de diarisation inconnu : {provider_id}") from exc
    return provider_factory(dict(options or {}))
