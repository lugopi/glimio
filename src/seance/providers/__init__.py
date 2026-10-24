"""Provider contracts and implementations for optional AI/media engines.

This package belongs to the Python application layer. Providers must not import
FastAPI, web services, or frontend code; presentation layers consume the neutral
metadata and events defined here.
"""

from .contracts import ProviderEvent, ProviderInfo, ProviderOption, ProviderOptionChoice, ProviderResourceLink, ProviderStatus
from .factory import (
    DEFAULT_TEXT_PROVIDER,
    DEFAULT_TRANSCRIPTION_PROVIDER,
    TEXT_PROVIDER_IDS,
    TRANSCRIPTION_PROVIDER_IDS,
    create_text_provider,
    create_transcription_provider,
    registered_provider_infos,
)
from .registry import default_provider_options, get_provider_info, get_provider_statuses, normalize_provider_options

__all__ = [
    "DEFAULT_TEXT_PROVIDER", "DEFAULT_TRANSCRIPTION_PROVIDER", "TEXT_PROVIDER_IDS",
    "TRANSCRIPTION_PROVIDER_IDS", "ProviderEvent",
    "ProviderInfo", "ProviderOption", "ProviderOptionChoice", "ProviderResourceLink", "ProviderStatus", "create_text_provider",
    "create_transcription_provider",
    "default_provider_options", "get_provider_info", "get_provider_statuses", "normalize_provider_options",
    "registered_provider_infos",
]
