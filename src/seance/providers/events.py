"""Execution-local provider event routing shared by CLI and Web use cases."""
from __future__ import annotations

from contextvars import ContextVar, Token

from .contracts import ProviderEvent, ProviderEventCallback


_EVENT_CALLBACK: ContextVar[ProviderEventCallback | None] = ContextVar(
    "glimio_provider_event_callback", default=None,
)


def set_provider_event_callback(callback: ProviderEventCallback | None) -> Token[ProviderEventCallback | None]:
    return _EVENT_CALLBACK.set(callback)


def reset_provider_event_callback(token: Token[ProviderEventCallback | None]) -> None:
    _EVENT_CALLBACK.reset(token)


def emit_provider_event(event: ProviderEvent, callback: ProviderEventCallback | None = None) -> None:
    """Deliver an event to the current use-case listener without coupling to a UI."""
    listener = callback or _EVENT_CALLBACK.get()
    if listener is not None:
        try:
            listener(event)
        except Exception:
            # Progress reporting is advisory and cannot fail model work.
            pass
