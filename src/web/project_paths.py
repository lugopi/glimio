"""Shared project and platform-specific executable paths."""
from seance.project_paths import (
    DEFAULT_DEEP_FILTER_EXECUTABLE_PATH, DEFAULT_LLAMA_COMPLETION_PATH,
    DEFAULT_WHISPER_CLI_PATH, discover_project_root, resolve_session_root,
)

__all__ = [
    "DEFAULT_DEEP_FILTER_EXECUTABLE_PATH", "DEFAULT_LLAMA_COMPLETION_PATH",
    "DEFAULT_WHISPER_CLI_PATH", "discover_project_root", "resolve_session_root",
]
