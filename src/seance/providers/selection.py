"""Context-local provider selection for use cases without UI dependencies."""
from __future__ import annotations

from contextvars import ContextVar, Token


_TEXT_PROVIDER: ContextVar[tuple[str | None, dict[str, object]]] = ContextVar(
    "glimio_text_provider", default=(None, {}),
)


def set_text_provider(
    provider_id: str | None,
    options: dict[str, object] | None = None,
) -> Token[tuple[str | None, dict[str, object]]]:
    return _TEXT_PROVIDER.set((provider_id, dict(options or {})))


def reset_text_provider(token: Token[tuple[str | None, dict[str, object]]]) -> None:
    _TEXT_PROVIDER.reset(token)


def selected_text_provider(default: str) -> str:
    return _TEXT_PROVIDER.get()[0] or default


def selected_text_provider_options() -> dict[str, object]:
    return dict(_TEXT_PROVIDER.get()[1])
