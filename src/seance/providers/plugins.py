"""Optional provider plug-ins loaded through Python package entry points.

A third-party distribution can expose an adapter without changing Glimio's
orchestration or either application entry point. Plug-ins remain optional: a
broken optional integration is reported as a warning and does not prevent the
CLI or Web app from starting.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Any
import warnings

from .contracts import ProviderInfo

PROVIDER_ENTRY_POINT_GROUP = "glimio.providers"
# These IDs are owned by Glimio's built-in adapters and cannot be replaced by
# an installed entry point. This also keeps a plugin from shadowing a provider
# of another task through the shared global catalogue.
RESERVED_PROVIDER_IDS = frozenset({
    "llama.cpp", "whisper.cpp", "sherpa-onnx", "ffmpeg", "native",
    "no-enhancement", "ffmpeg-denoise", "deepfilternet", "no-separation",
    "speechbrain-sepformer", "none-speaker-embedding", "speechbrain-ecapa",
})
SUPPORTED_PLUGIN_TASKS = frozenset({
    "generation", "transcription", "diarization", "media", "enhancement",
    "separation", "speaker_embedding",
})

# A readiness callback returns (missing resources, JSON-compatible diagnostics).
ReadinessCheck = Callable[[Mapping[str, Any], Path], tuple[tuple[str, ...], Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class ProviderPlugin:
    """A plug-in adapter registered by an installed Python distribution.

    ``factory`` must implement the constructor contract for ``info.task``; see
    docs/PROVIDERS.md for the per-task constructor signatures. It may be a class
    or a function returning an implementation of the relevant provider Protocol.
    """

    info: ProviderInfo
    factory: Callable[..., Any]
    readiness: ReadinessCheck | None = None

    def __post_init__(self) -> None:
        if self.info.task not in SUPPORTED_PLUGIN_TASKS:
            raise ValueError(f"Tâche de provider non prise en charge : {self.info.task}")
        if not callable(self.factory):
            raise TypeError(f"La fabrique du provider {self.info.id} doit être appelable.")
        if self.readiness is not None and not callable(self.readiness):
            raise TypeError(f"Le diagnostic du provider {self.info.id} doit être appelable.")


def _coerce_plugin(target: Any) -> ProviderPlugin:
    """Accept an exported ProviderPlugin or an adapter class exposing ``info``."""
    if isinstance(target, ProviderPlugin):
        return target

    # An entry point can instead target a zero-argument function returning a
    # ProviderPlugin. Adapter classes expose ``info`` directly and are not called
    # here, because their constructors require task-specific arguments.
    info = getattr(target, "info", None)
    if not isinstance(info, ProviderInfo) and callable(target):
        target = target()
        if isinstance(target, ProviderPlugin):
            return target
        info = getattr(target, "info", None)

    if not isinstance(info, ProviderInfo) or not callable(target):
        raise TypeError(
            "La cible d’un entry point Glimio doit exposer ProviderPlugin ou "
            "une fabrique/adaptateur appelable avec un attribut `info: ProviderInfo`."
        )
    readiness = getattr(target, "check_readiness", None)
    return ProviderPlugin(info=info, factory=target, readiness=readiness)


@lru_cache(maxsize=1)
def load_provider_plugins() -> tuple[ProviderPlugin, ...]:
    """Load ``glimio.providers`` entry points once, in deterministic order.

    Invalid plug-ins are isolated from the rest of the app. Duplicate IDs are
    ignored after the first registration to make results deterministic.
    """
    discovered = entry_points()
    if hasattr(discovered, "select"):
        matches = list(discovered.select(group=PROVIDER_ENTRY_POINT_GROUP))
    else:  # pragma: no cover - compatibility with older importlib.metadata APIs
        matches = list(discovered.get(PROVIDER_ENTRY_POINT_GROUP, ()))

    plugins: list[ProviderPlugin] = []
    seen_ids: set[str] = set()
    for entry_point in sorted(matches, key=lambda item: (item.name, item.value)):
        try:
            plugin = _coerce_plugin(entry_point.load())
            if plugin.info.id in RESERVED_PROVIDER_IDS:
                raise ValueError(f"Identifiant réservé à un provider intégré : {plugin.info.id}")
            if plugin.info.id in seen_ids:
                raise ValueError(f"Identifiant de provider dupliqué : {plugin.info.id}")
            seen_ids.add(plugin.info.id)
            plugins.append(plugin)
        except Exception as exc:
            warnings.warn(
                f"Provider Glimio ignoré ({entry_point.name}): {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
    return tuple(plugins)


def check_plugin_readiness(
    plugin: ProviderPlugin,
    options: Mapping[str, Any],
    project_root: Path,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Run an optional plugin diagnostic without letting one adapter break the catalogue."""
    if plugin.readiness is None:
        return (), {}
    try:
        missing, details = plugin.readiness(options, project_root)
        return tuple(str(item) for item in missing), dict(details)
    except Exception as exc:
        return (f"Diagnostic du provider en échec ({type(exc).__name__})",), {
            "readiness_error": str(exc),
        }


def plugins_for_task(task: str) -> tuple[ProviderPlugin, ...]:
    """Return discovered plug-ins for one provider task."""
    return tuple(plugin for plugin in load_provider_plugins() if plugin.info.task == task)


def get_provider_plugin(provider_id: str) -> ProviderPlugin | None:
    """Return a plug-in registration by stable provider ID, if installed."""
    return next((plugin for plugin in load_provider_plugins() if plugin.info.id == provider_id), None)
