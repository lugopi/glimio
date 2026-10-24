"""llama.cpp text-generation adapter."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from ..llm import run_completion_once, run_completion_resilient
from ..project_paths import DEFAULT_LLAMA_COMPLETION_PATH
from .contracts import GenerationRequest, GenerationResult, ProviderEvent, ProviderInfo, ProviderOption, ProviderOptionChoice, ProviderResourceLink
from .events import emit_provider_event


LLAMA_CPP_TRANSLATIONS_EN = {'en': {'Génération locale de résumés et réponses à partir de modèles GGUF.': 'Local generation of summaries '
                                                                              'and answers using GGUF '
                                                                              'models.',
        'Modèle de résumé': 'Summary model',
        'Fichier GGUF utilisé pour les résumés et les réponses de recherche.': 'GGUF file used for summaries '
                                                                               'and search answers.',
        'Moteur de résumé': 'Summary engine',
        'Exécutable llama.cpp fourni avec l’installation.': 'llama.cpp executable included with the '
                                                            'installation.',
        'Utiliser OpenVINO': 'Use OpenVINO',
        'Facultatif. Demande un llama.cpp compilé avec le backend OpenVINO.': 'Optional. Requires llama.cpp '
                                                                              'built with the OpenVINO '
                                                                              'backend.',
        'Périphérique OpenVINO': 'OpenVINO device',
        'Choisissez le périphérique Intel pris en charge par votre installation.': 'Choose an Intel device '
                                                                                   'supported by your '
                                                                                   'installation.',
        'Binaires llama.cpp': 'llama.cpp binaries',
        'Téléchargez une archive adaptée à votre système et configurez l’exécutable ci-dessous.': 'Download '
                                                                                                  'an '
                                                                                                  'archive '
                                                                                                  'for your '
                                                                                                  'system '
                                                                                                  'and '
                                                                                                  'configure '
                                                                                                  'the '
                                                                                                  'executable '
                                                                                                  'below.',
        'Modèles GGUF': 'GGUF models',
        'Choisissez un modèle GGUF adapté à votre RAM/VRAM et à sa licence.': 'Choose a GGUF model suited to '
                                                                              'your RAM/VRAM and check its '
                                                                              'license.',
        'Documentation llama.cpp': 'llama.cpp documentation'}}


LLAMA_CPP_INFO = ProviderInfo(
    id="llama.cpp",
    name="llama.cpp",
    task="generation",
    description="Génération locale de résumés et réponses à partir de modèles GGUF.",
    execution="system_executable",
    capabilities=("local", "gguf", "cancellation", "retry"),
    setup_links=(
        ProviderResourceLink("Binaires llama.cpp", "https://github.com/ggml-org/llama.cpp/releases", "binary", "Téléchargez une archive adaptée à votre système et configurez l’exécutable ci-dessous."),
        ProviderResourceLink("Modèles GGUF", "https://huggingface.co/models?library=gguf&sort=trending", "model", "Choisissez un modèle GGUF adapté à votre RAM/VRAM et à sa licence."),
        ProviderResourceLink("Documentation llama.cpp", "https://github.com/ggml-org/llama.cpp", "documentation"),
    ),
    options=(
        ProviderOption(
            key="gguf", label="Modèle de résumé", type="path",
            default="models/llm/model.gguf",
            description="Fichier GGUF utilisé pour les résumés et les réponses de recherche.",
            required=True,
        ),
        ProviderOption(
            key="llama_completion", label="Moteur de résumé", type="path",
            default=DEFAULT_LLAMA_COMPLETION_PATH,
            description="Exécutable llama.cpp fourni avec l’installation.",
            required=True, advanced=True,
        ),
        ProviderOption(
            key="openvino_enabled", label="Utiliser OpenVINO", type="boolean",
            default=False,
            description="Facultatif. Demande un llama.cpp compilé avec le backend OpenVINO.",
            advanced=True,
        ),
        ProviderOption(
            key="openvino_device", label="Périphérique OpenVINO", type="select",
            default="CPU", description="Choisissez le périphérique Intel pris en charge par votre installation.",
            choices=(ProviderOptionChoice("CPU", "CPU"), ProviderOptionChoice("GPU", "GPU"), ProviderOptionChoice("NPU", "NPU")),
            advanced=True, depends_on="openvino_enabled",
        ),
    ),

    translations=LLAMA_CPP_TRANSLATIONS_EN,
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
        options: dict[str, Any] | None = None,
    ) -> None:
        options = options or {}
        self.working_directory = Path(working_directory).expanduser().resolve()
        configured_executable = Path(options.get("llama_completion", executable)).expanduser()
        configured_model = Path(options.get("gguf", model)).expanduser()
        self.executable = (
            configured_executable.resolve()
            if configured_executable.is_absolute()
            else (self.working_directory / configured_executable).resolve()
        )
        self.model = (
            configured_model.resolve()
            if configured_model.is_absolute()
            else (self.working_directory / configured_model).resolve()
        )
        self.cancel_event = cancel_event
        self.on_process = on_process
        self.timeout_seconds = timeout_seconds
        self.completion_runner = completion_runner
        # Backend-specific environment configuration stays inside this adapter.
        self.environment_overrides = {
            "GGML_OPENVINO_DEVICE": (
                str(options.get("openvino_device", "CPU"))
                if options.get("openvino_enabled") else None
            ),
        }

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
            environment_overrides=self.environment_overrides,
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
            environment_overrides=self.environment_overrides,
        )
        return GenerationResult(text=text, hit_token_limit=hit_limit)
