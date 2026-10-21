"""llama.cpp text-generation adapter."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from ..llm import run_completion_once, run_completion_resilient
from .contracts import GenerationRequest, GenerationResult, ProviderEvent, ProviderInfo
from .events import emit_provider_event


LLAMA_CPP_INFO = ProviderInfo(
    id="llama.cpp",
    name="llama.cpp",
    task="generation",
    description="Génération locale de résumés et réponses à partir de modèles GGUF.",
    execution="system_executable",
    capabilities=("local", "gguf", "cancellation", "retry"),
)


class LlamaCppTextProvider:
    """Translate Glimio generation requests to the llama.cpp runner contract."""

    info = LLAMA_CPP_INFO

    def __init__(
        self,
        executable: str | Path,
        model: str | Path,
        working_directory: str | Path,
        *,
        cancel_event: threading.Event | None = None,
        on_process: Any = None,
        timeout_seconds: float | None = None,
        completion_runner=run_completion_resilient,
    ) -> None:
        self.executable = Path(executable)
        self.model = Path(model)
        self.working_directory = Path(working_directory)
        self.cancel_event = cancel_event
        self.on_process = on_process
        self.timeout_seconds = timeout_seconds
        self.completion_runner = completion_runner

    def generate(self, request: GenerationRequest, *, on_event=None) -> GenerationResult:
        emit_provider_event(ProviderEvent(
            provider_id=self.info.id, task="generation", stage="starting",
            message=f"{request.stage} · démarrage du moteur…",
        ), on_event)
        text, hit_limit = self.completion_runner(
            self.executable,
            self.model,
            self.working_directory,
            request.system_prompt,
            request.user_prompt,
            context=request.context_tokens,
            max_tokens=request.max_output_tokens,
            temperature=request.temperature,
            stage=request.stage,
            retries=request.retries,
            cancel_event=self.cancel_event,
            on_process=self.on_process,
            timeout_seconds=self.timeout_seconds,
        )
        emit_provider_event(ProviderEvent(
            provider_id=self.info.id, task="generation", stage="completed",
            message=f"{request.stage} · génération terminée",
            details={"hit_token_limit": hit_limit},
        ), on_event)
        return GenerationResult(text=text, hit_token_limit=hit_limit)

    def generate_once(self, request: GenerationRequest) -> GenerationResult:
        text, hit_limit = run_completion_once(
            self.executable,
            self.model,
            self.working_directory,
            request.system_prompt,
            request.user_prompt,
            context=request.context_tokens,
            max_tokens=request.max_output_tokens,
            temperature=request.temperature,
            stage=request.stage,
            cancel_event=self.cancel_event,
            on_process=self.on_process,
            timeout_seconds=self.timeout_seconds,
        )
        return GenerationResult(text=text, hit_token_limit=hit_limit)
