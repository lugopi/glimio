from __future__ import annotations

import argparse
import threading
from pathlib import Path
from typing import Any

import pytest

from seance.processing import diarization_process
from seance.processing.diarization_process import (
    _diarization_config,
    _run_diarization_child,
    diarize_transcription_isolated,
)


class _FakeConnection:
    def __init__(self) -> None:
        self.peer: _FakeConnection | None = None
        self.received: list[tuple[str, str]] = []
        self.closed = False

    def send(self, value: tuple[str, str]) -> None:
        if self.peer is None:
            self.received.append(value)
        else:
            self.peer.received.append(value)

    def close(self) -> None:
        self.closed = True

    def poll(self, timeout: float | None = None) -> bool:
        return bool(self.received)

    def recv(self) -> tuple[str, str]:
        return self.received.pop(0)


class _FakePipe:
    def __init__(self) -> None:
        self.parent = _FakeConnection()
        self.child = _FakeConnection()
        self.parent.peer = self.child
        self.child.peer = self.parent


class _FakeProcess:
    def __init__(
        self,
        target: Any,
        args: tuple[Any, ...],
        *,
        run_target: bool,
        stays_alive: bool = False,
        on_start: Any = None,
        **kwargs: Any,
    ) -> None:
        self.target = target
        self.args = args
        self.run_target = run_target
        self.stays_alive = stays_alive
        self.on_start = on_start
        self.alive = False
        self.exitcode: int | None = None
        self.terminated = False
        self.kwargs = kwargs

    def start(self) -> None:
        if self.on_start is not None:
            self.on_start()
        if self.run_target:
            self.target(*self.args)
            self.exitcode = 0
            return
        self.alive = self.stays_alive

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        return

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def kill(self) -> None:
        self.terminate()


class _FakeContext:
    def __init__(
        self,
        *,
        run_target: bool,
        stays_alive: bool = False,
        on_start: Any = None,
    ) -> None:
        self.pipe = _FakePipe()
        self.run_target = run_target
        self.stays_alive = stays_alive
        self.on_start = on_start
        self.process: _FakeProcess | None = None

    def Pipe(self, duplex: bool = True) -> tuple[_FakeConnection, _FakeConnection]:
        assert duplex is False
        return self.pipe.parent, self.pipe.child

    def Process(self, target: Any, args: tuple[Any, ...], **kwargs: Any) -> _FakeProcess:
        self.process = _FakeProcess(
            target,
            args,
            run_target=self.run_target,
            stays_alive=self.stays_alive,
            on_start=self.on_start,
            **kwargs,
        )
        return self.process


def _install_fake_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_target: bool,
    stays_alive: bool = False,
    on_start: Any = None,
) -> _FakeContext:
    context = _FakeContext(run_target=run_target, stays_alive=stays_alive, on_start=on_start)
    monkeypatch.setattr(diarization_process.mp, "get_context", lambda method: context)
    return context


def _args(**overrides: Any) -> argparse.Namespace:
    values = {
        "diarization_segmentation_model": "seg.onnx",
        "diarization_embedding_model": "emb.onnx",
        "diarization_num_speakers": -1,
        "diarization_threshold": 0.5,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_diarization_config_keeps_only_serializable_options() -> None:
    args = _args(
        diarization_num_speakers=3,
        diarization_threshold=0.4,
        status_callback=lambda message: None,
        _cancel_event=threading.Event(),
    )

    assert _diarization_config(args) == {
        "diarization_segmentation_model": "seg.onnx",
        "diarization_embedding_model": "emb.onnx",
        "diarization_num_speakers": 3,
        "diarization_threshold": 0.4,
    }


def test_child_runs_diarization_and_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_diarize(folder: str, args: argparse.Namespace, *, backup_existing: bool = False) -> dict[str, Any]:
        captured["folder"] = folder
        captured["args"] = args
        captured["backup_existing"] = backup_existing
        return {"speakers": {}, "segments": []}

    monkeypatch.setattr("seance.processing.diarization.diarize_transcription", fake_diarize)
    connection = _FakeConnection()

    _run_diarization_child(connection, str(tmp_path), {"diarization_num_speakers": 2}, True)

    assert connection.received == [("ok", "")]
    assert captured["folder"] == str(tmp_path)
    assert captured["args"].diarization_num_speakers == 2
    assert captured["backup_existing"] is True


def test_child_reports_actionable_diarization_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_diarize(folder: str, args: argparse.Namespace, *, backup_existing: bool = False) -> dict[str, Any]:
        raise SystemExit("Aucun tour de parole n'a été détecté.")

    monkeypatch.setattr("seance.processing.diarization.diarize_transcription", fake_diarize)
    connection = _FakeConnection()

    _run_diarization_child(connection, str(tmp_path), {}, True)

    assert connection.received == [("error", "Aucun tour de parole n'a été détecté.")]


def test_child_reports_unexpected_diarization_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_diarize(folder: str, args: argparse.Namespace, *, backup_existing: bool = False) -> dict[str, Any]:
        raise RuntimeError("native failure")

    monkeypatch.setattr("seance.processing.diarization.diarize_transcription", fake_diarize)
    connection = _FakeConnection()

    _run_diarization_child(connection, str(tmp_path), {}, True)

    assert connection.received == [("error", "RuntimeError: native failure")]


def test_isolated_diarization_propagates_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, argparse.Namespace, bool]] = []

    def fake_diarize(folder: str, args: argparse.Namespace, *, backup_existing: bool = False) -> dict[str, Any]:
        calls.append((folder, args, backup_existing))
        return {"speakers": {}, "segments": []}

    monkeypatch.setattr("seance.processing.diarization.diarize_transcription", fake_diarize)
    context = _install_fake_context(monkeypatch, run_target=True)

    diarize_transcription_isolated(tmp_path, _args(diarization_num_speakers=2), backup_existing=True)

    assert context.process is not None
    assert context.process.kwargs["daemon"] is True
    assert calls[0][0] == str(tmp_path.resolve())
    assert calls[0][1].diarization_num_speakers == 2
    assert calls[0][2] is True


def test_isolated_diarization_propagates_child_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_diarize(folder: str, args: argparse.Namespace, *, backup_existing: bool = False) -> dict[str, Any]:
        raise SystemExit("Modèle absent")

    monkeypatch.setattr("seance.processing.diarization.diarize_transcription", fake_diarize)
    _install_fake_context(monkeypatch, run_target=True)

    with pytest.raises(SystemExit, match="Modèle absent"):
        diarize_transcription_isolated(tmp_path, _args())


def test_isolated_diarization_reports_missing_child_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _install_fake_context(monkeypatch, run_target=False)

    with pytest.raises(SystemExit, match="sans résultat"):
        diarize_transcription_isolated(tmp_path, _args())

    assert context.process is not None


def test_isolated_diarization_does_not_spawn_when_already_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _install_fake_context(monkeypatch, run_target=False, stays_alive=True)
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(SystemExit, match="annulé"):
        diarize_transcription_isolated(tmp_path, _args(), cancel_event=cancel_event)

    assert context.process is None


def test_isolated_diarization_terminates_child_on_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancel_event = threading.Event()
    context = _install_fake_context(
        monkeypatch,
        run_target=False,
        stays_alive=True,
        on_start=cancel_event.set,
    )

    with pytest.raises(SystemExit, match="annulé"):
        diarize_transcription_isolated(tmp_path, _args(), cancel_event=cancel_event)

    assert context.process is not None
    assert context.process.terminated is True
