"""Context-local provider selection for use cases without UI dependencies."""
from __future__ import annotations

from contextvars import ContextVar, Token


_TEXT_PROVIDER: ContextVar[str | None] = ContextVar("glimio_text_provider", default=None)


def set_text_provider(provider_id: str | None) -> Token[str | None]:
    return _TEXT_PROVIDER.set(provider_id)


def reset_text_provider(token: Token[str | None]) -> None:
    _TEXT_PROVIDER.reset(token)


def selected_text_provider(default: str) -> str:
    return _TEXT_PROVIDER.get() or default
