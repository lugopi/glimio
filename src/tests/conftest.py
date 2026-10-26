"""Shared test-session settings.

Windows can report ``WinError 145`` when a temporary directory is removed while
SQLite or a background writer is still releasing the last handle, even though
the directory is already empty. ``tempfile.TemporaryDirectory.cleanup`` calls
``shutil.rmtree``, so retrying that call briefly makes the suite deterministic
without hiding a real, persistent cleanup failure.
"""
from __future__ import annotations

import shutil
import time
from typing import Any, Callable

import pytest

_RETRY_ATTEMPTS = 10
_RETRY_DELAY_SECONDS = 0.05


@pytest.fixture(scope="session", autouse=True)
def _retry_transient_temp_cleanup() -> Any:
    original: Callable[..., Any] = shutil.rmtree

    def retrying_rmtree(path: Any, *args: Any, **kwargs: Any) -> Any:
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return original(path, *args, **kwargs)
            except FileNotFoundError:
                return None
            except OSError:
                if attempt == _RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_RETRY_DELAY_SECONDS)
        return None

    shutil.rmtree = retrying_rmtree
    try:
        yield
    finally:
        shutil.rmtree = original
