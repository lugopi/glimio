"""Process-wide synchronization for local AI engines used by the Web application.

Audio capture deliberately does not acquire this lock: a recording can continue while
an existing session is transcribed or summarized. Whisper and llama.cpp do acquire it
so they do not load and execute heavyweight models concurrently in the same process.
"""
from __future__ import annotations

import threading

AI_ENGINE_LOCK = threading.Lock()


def acquire_ai_engine(cancel_event: threading.Event | None = None) -> bool:
    """Acquire the local AI engine slot, remaining responsive to cancellation.

    Returns ``False`` only when a caller's cancellation event is set before the slot
    becomes available. Callers that acquire the slot must release ``AI_ENGINE_LOCK``.
    """
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return False
        if AI_ENGINE_LOCK.acquire(timeout=0.25):
            return True
