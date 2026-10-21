"""Compatibility exports for path helpers now owned by the Python core."""
from seance.project_paths import discover_project_root, resolve_session_root

__all__ = ["discover_project_root", "resolve_session_root"]
