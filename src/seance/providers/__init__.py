"""Provider contracts and implementations for optional AI/media engines.

This package belongs to the Python application layer. Providers must not import
FastAPI, web services, or frontend code; presentation layers consume the neutral
metadata and events defined here.
"""

from .contracts import ProviderEvent, ProviderInfo, ProviderStatus
from .factory import (
    DEFAULT_TEXT_PROVIDER,
    DEFAULT_TRANSCRIPTION_PROVIDER,
    TEXT_PROVIDER_IDS,
    TRANSCRIPTION_PROVIDER_IDS,
    create_text_provider,
    create_transcription_provider,
)
from .registry import get_provider_statuses

__all__ = [
    "DEFAULT_TEXT_PROVIDER", "DEFAULT_TRANSCRIPTION_PROVIDER", "TEXT_PROVIDER_IDS",
    "TRANSCRIPTION_PROVIDER_IDS", "ProviderEvent",
    "ProviderInfo", "ProviderStatus", "create_text_provider",
    "create_transcription_provider",
    "get_provider_statuses",
]
