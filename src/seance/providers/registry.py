"""Built-in provider catalogue and lightweight readiness checks."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from .contracts import ProviderInfo, ProviderStatus
from .llama_cpp import LLAMA_CPP_INFO
from .whisper_cpp import WHISPER_CPP_INFO


BUILTIN_PROVIDERS = (
    WHISPER_CPP_INFO,
    LLAMA_CPP_INFO,
    ProviderInfo(
        id="sherpa-onnx", name="sherpa-onnx", task="diarization",
        description="Diarisation locale avec modèles ONNX.",
        execution="embedded",
        capabilities=("local", "speaker-segmentation", "speaker-embedding"),
    ),
    ProviderInfo(
        id="ffmpeg", name="FFmpeg", task="media",
        description="Décodage et conversion des formats audio/vidéo importés.",
        execution="system_executable",
        capabilities=("audio-video-import", "audio-chunking"),
    ),
)


def _resolved_path(value: str | Path | None, root: Path) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def get_provider_statuses(settings: Any, *, project_root: str | Path) -> list[ProviderStatus]:
    """Describe built-in providers and report whether their configured resources exist.

    This probes only local paths and import availability. It never launches a provider
    executable or downloads a model as a side effect of opening the settings page.
    """
    root = Path(project_root).expanduser().resolve()
    whisper_binary = _resolved_path(getattr(settings, "whisper_cli", None), root)
    whisper_model = _resolved_path(getattr(settings, "model", None), root)
    llama_binary = _resolved_path(getattr(settings, "llama_completion", None), root)
    llama_model = _resolved_path(getattr(settings, "gguf", None), root)
    segmentation = _resolved_path(getattr(settings, "diarization_segmentation_model", None), root)
    embedding = _resolved_path(getattr(settings, "diarization_embedding_model", None), root)
    ffmpeg_setting = str(getattr(settings, "ffmpeg", "ffmpeg") or "ffmpeg").strip()
    ffmpeg_candidate = _resolved_path(ffmpeg_setting, root) if ("/" in ffmpeg_setting or "\\" in ffmpeg_setting) else None
    ffmpeg_found = ffmpeg_candidate if ffmpeg_candidate is not None else shutil.which(ffmpeg_setting)

    specs = (
        (BUILTIN_PROVIDERS[0], (whisper_binary, whisper_model), {
            "executable": str(whisper_binary) if whisper_binary else None,
            "model": str(whisper_model) if whisper_model else None,
        }),
        (BUILTIN_PROVIDERS[1], (llama_binary, llama_model), {
            "executable": str(llama_binary) if llama_binary else None,
            "model": str(llama_model) if llama_model else None,
        }),
        (BUILTIN_PROVIDERS[2], (segmentation, embedding), {
            "package_available": importlib.util.find_spec("sherpa_onnx") is not None,
            "segmentation_model": str(segmentation) if segmentation else None,
            "embedding_model": str(embedding) if embedding else None,
        }),
    )
    statuses: list[ProviderStatus] = []
    for provider, paths, details in specs:
        missing = tuple(str(path) for path in paths if path is None or not path.is_file())
        if provider.id == "sherpa-onnx" and not details["package_available"]:
            missing = (*missing, "Python package sherpa-onnx")
        ready = not missing
        statuses.append(ProviderStatus(
            provider=provider,
            ready=ready,
            message="Prêt" if ready else "Ressources manquantes",
            missing=missing,
            details=details,
        ))

    ffmpeg_missing = () if ffmpeg_found and (not isinstance(ffmpeg_found, Path) or ffmpeg_found.is_file()) else (ffmpeg_setting,)
    statuses.append(ProviderStatus(
        provider=BUILTIN_PROVIDERS[3],
        ready=not ffmpeg_missing,
        message="Prêt" if not ffmpeg_missing else "FFmpeg introuvable",
        missing=ffmpeg_missing,
        details={"executable": str(ffmpeg_found) if ffmpeg_found else ffmpeg_setting},
    ))
    return statuses
