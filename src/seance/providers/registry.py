"""Built-in provider catalogue and lightweight readiness checks."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from .contracts import ProviderInfo, ProviderOption, ProviderOptionChoice, ProviderResourceLink, ProviderStatus
from .factory import registered_provider_infos
from .audio_processing import provider_readiness
from .media_tools import MEDIA_PROVIDER_IDS, media_toolchain_status
from .plugins import check_plugin_readiness, get_provider_plugin, load_provider_plugins


ALL_PROVIDER_INFOS = registered_provider_infos()
_PLUGIN_INFO_OBJECT_IDS = {id(plugin.info) for plugin in load_provider_plugins()}
BUILTIN_PROVIDERS = tuple(info for info in ALL_PROVIDER_INFOS if id(info) not in _PLUGIN_INFO_OBJECT_IDS)
PROVIDERS_BY_ID = {provider.id: provider for provider in ALL_PROVIDER_INFOS}


def get_provider_info(provider_id: str) -> ProviderInfo | None:
    return PROVIDERS_BY_ID.get(provider_id)


def default_provider_options() -> dict[str, dict[str, Any]]:
    return {
        provider.id: {option.key: option.default for option in provider.options}
        for provider in ALL_PROVIDER_INFOS if provider.options
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
    importlib.invalidate_caches()
    root = Path(project_root).expanduser().resolve()
    provider_options = getattr(settings, "provider_options", {}) or {}
    sherpa_options = provider_options.get("sherpa-onnx", {})
    segmentation = _resolved_path(sherpa_options.get("diarization_segmentation_model", getattr(settings, "diarization_segmentation_model", None)), root)
    embedding = _resolved_path(sherpa_options.get("diarization_embedding_model", getattr(settings, "diarization_embedding_model", None)), root)

    statuses: list[ProviderStatus] = []
    for provider in ALL_PROVIDER_INFOS:
        plugin = get_provider_plugin(provider.id)
        if plugin is not None and plugin.info is provider and plugin.readiness is not None:
            configured = provider_options.get(provider.id, {})
            configured = dict(configured) if isinstance(configured, dict) else {}
            missing, details = check_plugin_readiness(plugin, configured, root)
        elif provider.id in {"no-enhancement", "no-separation", "none-speaker-embedding"}:
            missing = ()
            details = {"dependencies": list(provider.requires)}
        elif provider.id in {"deepfilternet", "speechbrain-sepformer", "speechbrain-ecapa"}:
            configured = provider_options.get(provider.id, {})
            configured_paths = dict(configured) if isinstance(configured, dict) else {}
            for option in provider.options:
                if option.type == "path" and configured_paths.get(option.key) is not None:
                    raw_text = str(configured_paths[option.key]).strip()
                    raw_path = Path(raw_text).expanduser() if raw_text else None
                    is_bare_executable = (
                        option.path_role == "executable"
                        and raw_path is not None
                        and not raw_path.is_absolute()
                        and "/" not in raw_text
                        and "\\" not in raw_text
                    )
                    if not is_bare_executable:
                        resolved = _resolved_path(configured_paths[option.key], root)
                        configured_paths[option.key] = str(resolved) if resolved else configured_paths[option.key]
            ready, provider_missing = provider_readiness(provider, configured_paths)
            missing = provider_missing
            details = {"dependencies": list(provider.requires)}
        elif provider.id == "sherpa-onnx":
            details = {
                "package_available": importlib.util.find_spec("sherpa_onnx") is not None,
                "segmentation_model": str(segmentation) if segmentation else None,
                "embedding_model": str(embedding) if embedding else None,
            }
            paths = (segmentation, embedding)
            missing = tuple(str(path) for path in paths if path is None or not path.is_file())
            if not details["package_available"]:
                missing = (*missing, "Python package sherpa-onnx")
        elif provider.id == "whisper.cpp":
            configured = provider_options.get(provider.id, {})
            configured = dict(configured) if isinstance(configured, dict) else {}
            missing_values: list[str] = []
            details = {}
            for option in provider.options:
                value = configured.get(option.key, option.default)
                if option.type != "path":
                    continue
                raw_text = str(value).strip() if value is not None else ""
                raw_path = Path(raw_text).expanduser() if raw_text else None
                is_bare_executable = (
                    option.path_role == "executable"
                    and raw_path is not None
                    and not raw_path.is_absolute()
                    and "/" not in raw_text
                    and "\\" not in raw_text
                )
                if is_bare_executable:
                    executable = shutil.which(raw_text)
                    details[option.key] = executable or raw_text
                    if option.required and executable is None:
                        missing_values.append(raw_text or option.label)
                    continue
                resolved = _resolved_path(value, root)
                details[option.key] = str(resolved) if resolved else None
                if option.required and (resolved is None or not resolved.is_file()):
                    missing_values.append(str(resolved or option.label))

            vad_mode = str(configured.get("vad_mode", "auto") or "auto").strip().lower()
            vad_model = _resolved_path(configured.get("vad_model", "models/asr/ggml-silero-v6.2.0.bin"), root)
            vad_available = bool(vad_model and vad_model.is_file())
            details["vad_model_path"] = str(vad_model) if vad_model else None
            details["vad_model_available"] = vad_available
            if vad_mode != "off" and not vad_available:
                if vad_mode == "on":
                    missing_values.append(str(vad_model or "Modèle VAD Silero"))
                elif vad_mode == "auto":
                    details["warnings"] = [
                        "Modèle VAD Silero introuvable : le mode automatique désactive temporairement le VAD."
                    ]
            missing = tuple(missing_values)
        elif provider.id in MEDIA_PROVIDER_IDS:
            configured = provider_options.get(provider.id, {})
            configured = dict(configured) if isinstance(configured, dict) else {}
            if provider.id == "ffmpeg":
                configured.setdefault("ffmpeg", str(getattr(settings, "ffmpeg", "ffmpeg") or "ffmpeg"))
                configured.setdefault("ffprobe", str(getattr(settings, "ffprobe", "ffprobe") or "ffprobe"))
            missing, details = media_toolchain_status(provider, configured, root)
        else:
            configured = provider_options.get(provider.id, {})
            missing_values = []
            details = {}
            for option in provider.options:
                value = configured.get(option.key, option.default)
                if option.type == "path":
                    raw_text = str(value).strip() if value is not None else ""
                    raw_path = Path(raw_text).expanduser() if raw_text else None
                    is_bare_executable = (
                        option.path_role == "executable"
                        and raw_path is not None
                        and not raw_path.is_absolute()
                        and "/" not in raw_text
                        and "\\" not in raw_text
                    )
                    if is_bare_executable:
                        executable = shutil.which(raw_text)
                        details[option.key] = executable or raw_text
                        if option.required and executable is None:
                            missing_values.append(raw_text or option.label)
                    else:
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
    readiness = {status.provider.id: status.ready for status in statuses}
    resolved: list[ProviderStatus] = []
    for status in statuses:
        missing_dependencies = tuple(
            dependency for dependency in status.provider.requires if not readiness.get(dependency, False)
        )
        if missing_dependencies:
            missing = tuple(dict.fromkeys((*status.missing, *(f"provider requis : {item}" for item in missing_dependencies))))
            resolved.append(ProviderStatus(
                provider=status.provider, ready=False,
                message="Dépendance provider manquante", version=status.version,
                missing=missing, details={**status.details, "missing_provider_dependencies": list(missing_dependencies)},
            ))
        else:
            resolved.append(status)
    return resolved
