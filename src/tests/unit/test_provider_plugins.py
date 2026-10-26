from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from seance.providers.contracts import ProviderInfo, ProviderOption
from seance.providers.plugins import ProviderPlugin, _coerce_plugin, load_provider_plugins


def _info(provider_id: str = "example-test") -> ProviderInfo:
    return ProviderInfo(
        id=provider_id,
        name="Example",
        task="diarization",
        description="Test adapter",
        execution="embedded",
        options=(ProviderOption(key="model_path", label="Model", type="path", default="model.onnx"),),
    )


def test_provider_plugin_accepts_metadata_factory_and_readiness() -> None:
    class ExampleProvider:
        info = _info()

    def readiness(options, root: Path):
        return (), {"root": str(root), "configured": bool(options)}

    plugin = ProviderPlugin(info=ExampleProvider.info, factory=ExampleProvider, readiness=readiness)
    assert _coerce_plugin(plugin) is plugin
    assert _coerce_plugin(ExampleProvider).factory is ExampleProvider


def test_provider_plugin_rejects_unsupported_tasks() -> None:
    invalid = ProviderInfo(
        id="invalid-task", name="Invalid", task="unknown", description="Invalid", execution="embedded",  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="Tâche de provider"):
        ProviderPlugin(info=invalid, factory=lambda options: object())


def test_entry_points_are_loaded_deterministically_and_failures_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from seance.providers import plugins

    info = _info("plugin-loaded-test")
    factory = lambda options: SimpleNamespace(info=info)  # noqa: E731

    class EntryPoint:
        def __init__(self, name: str, value: str, target):
            self.name = name
            self.value = value
            self.target = target

        def load(self):
            if isinstance(self.target, Exception):
                raise self.target
            return self.target

    class EntryPoints(list):
        def select(self, *, group: str):
            assert group == "glimio.providers"
            return self

    entry_points = EntryPoints([
        EntryPoint("z-plugin", "z:PLUGIN", ProviderPlugin(info, factory)),
        EntryPoint("a-broken", "a:PLUGIN", RuntimeError("broken optional plugin")),
    ])
    monkeypatch.setattr(plugins, "entry_points", lambda: entry_points)
    load_provider_plugins.cache_clear()
    try:
        with pytest.warns(RuntimeWarning, match="broken optional plugin"):
            loaded = load_provider_plugins()
        assert [item.info.id for item in loaded] == ["plugin-loaded-test"]
    finally:
        load_provider_plugins.cache_clear()


def test_builtin_provider_ids_cannot_be_shadowed_by_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    from seance.providers import plugins

    reserved = ProviderPlugin(_info("llama.cpp"), lambda options: object())

    class EntryPoint:
        name = "reserved"
        value = "reserved:PLUGIN"

        def load(self):
            return reserved

    class EntryPoints(list):
        def select(self, *, group: str):
            return self

    monkeypatch.setattr(plugins, "entry_points", lambda: EntryPoints([EntryPoint()]))
    load_provider_plugins.cache_clear()
    try:
        with pytest.warns(RuntimeWarning, match="Identifiant réservé"):
            assert load_provider_plugins() == ()
    finally:
        load_provider_plugins.cache_clear()


def test_duplicate_plugin_ids_keep_the_first_sorted_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    from seance.providers import plugins

    first = ProviderPlugin(_info("duplicate-test"), lambda options: object())
    second = ProviderPlugin(_info("duplicate-test"), lambda options: object())

    class EntryPoint:
        def __init__(self, name: str, target):
            self.name = name
            self.value = name
            self.target = target

        def load(self):
            return self.target

    class EntryPoints(list):
        def select(self, *, group: str):
            return self

    monkeypatch.setattr(plugins, "entry_points", lambda: EntryPoints([
        EntryPoint("z-second", second), EntryPoint("a-first", first),
    ]))
    load_provider_plugins.cache_clear()
    try:
        with pytest.warns(RuntimeWarning, match="Identifiant de provider dupliqué"):
            loaded = load_provider_plugins()
        assert len(loaded) == 1
        assert loaded[0] is first
    finally:
        load_provider_plugins.cache_clear()
