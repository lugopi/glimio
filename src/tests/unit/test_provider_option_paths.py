from __future__ import annotations

from pathlib import Path

from seance.providers.contracts import ProviderInfo, ProviderOption
from seance.providers.options import resolve_provider_option_paths


def _provider() -> ProviderInfo:
    return ProviderInfo(
        id="path-test", name="Path test", task="transcription",
        description="Test path semantics", execution="system_executable",
        options=(
            ProviderOption(key="model", label="Model", type="path", default="models/model.bin"),
            ProviderOption(key="command", label="Command", type="path", default="engine", path_role="executable"),
        ),
    )


def test_asset_paths_are_project_relative_but_bare_executable_stays_on_path(tmp_path: Path) -> None:
    values = resolve_provider_option_paths(
        _provider(), {"model": "models/custom.bin", "command": "custom-engine"}, tmp_path,
    )
    assert values["model"] == str((tmp_path / "models/custom.bin").resolve())
    assert values["command"] == "custom-engine"


def test_executable_with_directory_is_resolved_relative_to_project(tmp_path: Path) -> None:
    values = resolve_provider_option_paths(
        _provider(), {"command": "tools/custom-engine"}, tmp_path,
    )
    assert values["command"] == str((tmp_path / "tools/custom-engine").resolve())


def test_option_defaults_are_not_injected_by_path_resolver(tmp_path: Path) -> None:
    values = resolve_provider_option_paths(_provider(), {}, tmp_path)
    assert values == {}
