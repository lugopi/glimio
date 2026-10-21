"""Built-in provider catalogue and lightweight readiness checks."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from .contracts import ProviderInfo, ProviderOption, ProviderOptionChoice, ProviderStatus
from .factory import registered_provider_infos


BUILTIN_PROVIDERS = (
    *registered_provider_infos(),
    ProviderInfo(
        id="sherpa-onnx", name="sherpa-onnx", task="diarization",
        description="Diarisation locale avec modèles ONNX.",
        execution="embedded",
        capabilities=("local", "speaker-segmentation", "speaker-embedding"),
        options=(
            ProviderOption(
                key="diarization_segmentation_model", label="Modèle de segmentation", type="path",
                default="models/diarization/segmentation/segmentation.onnx",
                description="Modèle ONNX qui détecte les tours de parole.", required=True, advanced=True,
            ),
            ProviderOption(
                key="diarization_embedding_model", label="Modèle de reconnaissance des voix", type="path",
                default="models/diarization/embedding/embedding.onnx",
                description="Modèle ONNX qui regroupe les segments par voix.", required=True, advanced=True,
            ),
        ),
    ),
    ProviderInfo(
        id="ffmpeg", name="FFmpeg", task="media",
        description="Décodage et conversion des formats audio/vidéo importés.",
        execution="system_executable",
        capabilities=("audio-video-import", "audio-chunking"),
        options=(ProviderOption(
            key="ffmpeg", label="Commande FFmpeg", type="text", default="ffmpeg",
            description="Commande ou chemin vers FFmpeg.", required=True, advanced=True,
        ),),
    ),
)


PROVIDERS_BY_ID = {provider.id: provider for provider in BUILTIN_PROVIDERS}


def get_provider_info(provider_id: str) -> ProviderInfo | None:
    return PROVIDERS_BY_ID.get(provider_id)


def default_provider_options() -> dict[str, dict[str, Any]]:
    return {
        provider.id: {option.key: option.default for option in provider.options}
        for provider in BUILTIN_PROVIDERS if provider.options
    }


def normalize_provider_options(
    configured: Any,
    *,
    legacy_values: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge defaults, validate values and discard options for removed providers."""
    defaults = default_provider_options()
    if not isinstance(configured, dict):
        configured = {}
    legacy = legacy_values or {}
    normalized: dict[str, dict[str, Any]] = {}
    for provider_id, provider in PROVIDERS_BY_ID.items():
        if not provider.options:
            continue
        saved = configured.get(provider_id, {})
        if not isinstance(saved, dict):
            raise ValueError(f"Les options du provider {provider_id} doivent être un objet.")
        saved = dict(saved)
        if provider_id == "whisper.cpp":
            # Migrate the former single device field without turning the new
            # opt-in toggle on for old blank/automatic values.
            old_device = saved.get("openvino_device", legacy.get("openvino_device"))
            if "openvino_enabled" not in saved and old_device:
                saved["openvino_enabled"] = True
            if old_device in (None, ""):
                saved.pop("openvino_device", None)
        values = dict(defaults[provider_id])
        for option in provider.options:
            value = saved.get(option.key, legacy.get(option.key, values.get(option.key)))
            values[option.key] = _validate_option_value(provider_id, option, value)
        normalized[provider_id] = values
    return normalized


def _validate_option_value(provider_id: str, option: ProviderOption, value: Any) -> Any:
    if value is None and not option.required:
        return None
    if option.type in {"text", "path", "secret"}:
        if not isinstance(value, str) or (option.required and not value.strip()):
            raise ValueError(f"Option invalide « {option.label} » pour {provider_id}.")
        return value
    if option.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Option invalide « {option.label} » pour {provider_id}.")
        return value
    if option.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Option invalide « {option.label} » pour {provider_id}.")
        if option.minimum is not None and value < option.minimum:
            raise ValueError(f"{option.label} doit être supérieur ou égal à {option.minimum}.")
        if option.maximum is not None and value > option.maximum:
            raise ValueError(f"{option.label} doit être inférieur ou égal à {option.maximum}.")
        return value
    if option.type == "select":
        values = {choice.value for choice in option.choices}
        if not isinstance(value, str) or value not in values:
            raise ValueError(f"Option invalide « {option.label} » pour {provider_id}.")
        return value
    raise ValueError(f"Type d’option non pris en charge pour {provider_id}.")


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
    provider_options = getattr(settings, "provider_options", {}) or {}
    sherpa_options = provider_options.get("sherpa-onnx", {})
    segmentation = _resolved_path(sherpa_options.get("diarization_segmentation_model", getattr(settings, "diarization_segmentation_model", None)), root)
    embedding = _resolved_path(sherpa_options.get("diarization_embedding_model", getattr(settings, "diarization_embedding_model", None)), root)
    ffmpeg_options = provider_options.get("ffmpeg", {})
    ffmpeg_setting = str(ffmpeg_options.get("ffmpeg", getattr(settings, "ffmpeg", "ffmpeg")) or "ffmpeg").strip()
    ffmpeg_candidate = _resolved_path(ffmpeg_setting, root) if ("/" in ffmpeg_setting or "\\" in ffmpeg_setting) else None
    ffmpeg_found = ffmpeg_candidate if ffmpeg_candidate is not None else shutil.which(ffmpeg_setting)

    statuses: list[ProviderStatus] = []
    for provider in BUILTIN_PROVIDERS:
        if provider.id == "sherpa-onnx":
            details = {
                "package_available": importlib.util.find_spec("sherpa_onnx") is not None,
                "segmentation_model": str(segmentation) if segmentation else None,
                "embedding_model": str(embedding) if embedding else None,
            }
            paths = (segmentation, embedding)
            missing = tuple(str(path) for path in paths if path is None or not path.is_file())
            if not details["package_available"]:
                missing = (*missing, "Python package sherpa-onnx")
        elif provider.id == "ffmpeg":
            missing = () if ffmpeg_found and (not isinstance(ffmpeg_found, Path) or ffmpeg_found.is_file()) else (ffmpeg_setting,)
            details = {"executable": str(ffmpeg_found) if ffmpeg_found else ffmpeg_setting}
        else:
            configured = provider_options.get(provider.id, {})
            missing_values = []
            details = {}
            for option in provider.options:
                value = configured.get(option.key, option.default)
                if option.type == "path":
                    resolved = _resolved_path(value, root)
                    details[option.key] = str(resolved) if resolved else None
                    if option.required and (resolved is None or not resolved.is_file()):
                        missing_values.append(str(resolved or option.label))
                elif option.required and (value is None or (isinstance(value, str) and not value.strip())):
                    missing_values.append(option.label)
            missing = tuple(missing_values)
        ready = not missing
        statuses.append(ProviderStatus(
            provider=provider,
            ready=ready,
            message="Prêt" if ready else "Ressources manquantes",
            missing=missing,
            details=details,
        ))
    return statuses
