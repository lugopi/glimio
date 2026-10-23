"""Run the native diarization work outside the main Python process.

``sherpa-onnx`` performs its inference in native code but can keep the CPython
GIL for the whole call. When diarization runs inside the web process, that
prevents FastAPI, the SSE stream and every other Python thread from making
progress until the inference finishes. A spawned child process has its own GIL,
so the API stays responsive while the heavy native call runs.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path
import threading
from typing import Any

_DIARIZATION_KEYS = (
    "diarization_segmentation_model",
    "diarization_embedding_model",
    "diarization_num_speakers",
    "diarization_threshold",
)


def _diarization_config(args: argparse.Namespace) -> dict[str, Any]:
    """Return only the small, serializable subset needed by the child process."""
    return {key: getattr(args, key) for key in _DIARIZATION_KEYS if hasattr(args, key)}


def _run_diarization_child(
    connection: Any,
    folder: str,
    config: dict[str, Any],
    backup_existing: bool,
) -> None:
    """Child-process entry point. Report success or a user-facing error."""
    try:
        # Imported here so the parent never loads the native module before the
        # isolation boundary, and the child only pays the import cost when needed.
        from .diarization import diarize_transcription

        child_args = argparse.Namespace(**config)
        diarize_transcription(folder, child_args, backup_existing=backup_existing)
    except SystemExit as exc:
        detail = str(exc) or "La diarisation a échoué."
        try:
            connection.send(("error", detail))
        except (BrokenPipeError, EOFError, OSError):
            pass
    except BaseException as exc:  # noqa: BLE001 - the parent must see child failures
        try:
            connection.send(("error", f"{type(exc).__name__}: {exc}"))
        except (BrokenPipeError, EOFError, OSError):
            pass
    else:
        try:
            connection.send(("ok", ""))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def _stop_process(process: mp.Process) -> None:
    """Terminate a child that may be blocked inside native inference."""
    process.terminate()
    process.join(5)
    if process.is_alive():
        process.kill()
        process.join(5)


def diarize_transcription_isolated(
    folder: str | Path,
    args: argparse.Namespace,
    *,
    backup_existing: bool = False,
    cancel_event: threading.Event | None = None,
) -> None:
    """Run :func:`diarize_transcription` in a spawned child process.

    Only the diarization options are copied to the child. Status and artifact
    callbacks intentionally stay in the parent; their callers already emit the
    surrounding progress messages. Cancellation is handled by the parent, which
    can terminate the child even while native inference is in progress.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise SystemExit("Traitement annulé.")

    context = mp.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    try:
        process = context.Process(
            target=_run_diarization_child,
            args=(
                child_connection,
                str(Path(folder).expanduser().resolve()),
                _diarization_config(args),
                backup_existing,
            ),
            name="glimio-diarization",
            daemon=True,
        )
        process.start()
    except BaseException:
        parent_connection.close()
        child_connection.close()
        raise
    child_connection.close()

    try:
        while process.is_alive():
            if cancel_event is not None and cancel_event.is_set():
                _stop_process(process)
                raise SystemExit("Traitement annulé.")
            process.join(0.2)
        process.join()
        if not parent_connection.poll(1.0):
            code = process.exitcode
            detail = f"code {code}" if code is not None else "code inconnu"
            raise SystemExit(f"La diarisation a échoué : le processus enfant s'est arrêté sans résultat ({detail}).")
        status, detail = parent_connection.recv()
        if status != "ok":
            raise SystemExit(str(detail) or "La diarisation a échoué.")
    finally:
        parent_connection.close()
        if process.is_alive():
            _stop_process(process)
