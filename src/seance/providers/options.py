"""Provider-option normalization helpers shared by CLI, Web and use cases."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import ProviderInfo


def resolve_provider_option_paths(
    info: ProviderInfo | None,
    options: dict[str, Any] | None,
    project_root: str | Path,
) -> dict[str, Any]:
    """Resolve declared local assets relative to the Glimio project.

    Executable-role options may remain as a bare command (for PATH lookup); if an
    executable includes a directory or is absolute, it is resolved like a path.
    The helper intentionally only rewrites values actually supplied by the caller,
    leaving adapter defaults in charge when no explicit option was persisted.
    """
    values = dict(options or {})
    if info is None:
        return values
    root = Path(project_root).expanduser().resolve()
    for option in info.options:
        if option.type != "path" or option.key not in values:
            continue
        value = values.get(option.key)
        if value is None or not str(value).strip():
            continue
        raw_value = str(value)
        raw = Path(raw_value).expanduser()
        has_directory = "/" in raw_value or "\\" in raw_value
        if option.path_role == "executable" and not raw.is_absolute() and not has_directory:
            continue
        values[option.key] = str(raw.resolve() if raw.is_absolute() else (root / raw).resolve())
    return values
