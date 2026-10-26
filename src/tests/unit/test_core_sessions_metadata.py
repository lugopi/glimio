from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

import web.app as web_app
from seance.core.sessions import (
    SessionServiceError,
    mark_audio_outputs_stale,
    read_metadata,
    write_metadata,
)
from seance.providers.contracts import MediaToolchainUnavailable
from seance.providers.media_tools import ensure_media_toolchain_ready


def test_write_then_read_metadata_round_trip(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    folder.mkdir()
    metadata = {"title": "Réunion équipe", "title_source": "user", "nested": {"keep": True}}

    write_metadata(folder, metadata)

    path = folder / "metadata" / "seance.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == metadata
    assert read_metadata(folder) == metadata


def test_read_metadata_prefers_structured_file(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    (folder / "metadata").mkdir(parents=True)
    (folder / "metadata" / "seance.json").write_text(
        json.dumps({"title": "structuré"}), encoding="utf-8",
    )
    (folder / "seance.json").write_text(json.dumps({"title": "historique"}), encoding="utf-8")

    assert read_metadata(folder) == {"title": "structuré"}


def test_read_metadata_falls_back_to_legacy_file(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "seance.json").write_text(json.dumps({"title": "historique"}), encoding="utf-8")

    assert read_metadata(folder) == {"title": "historique"}


def test_write_metadata_updates_legacy_file_when_structured_absent(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    folder.mkdir()
    legacy = folder / "seance.json"
    legacy.write_text(json.dumps({"title": "historique"}), encoding="utf-8")

    write_metadata(folder, {"title": "mis à jour"})

    assert json.loads(legacy.read_text(encoding="utf-8")) == {"title": "mis à jour"}
    assert not (folder / "metadata" / "seance.json").exists()


def test_read_metadata_returns_empty_when_absent(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    folder.mkdir()

    assert read_metadata(folder) == {}


def test_read_metadata_rejects_non_object(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    (folder / "metadata").mkdir(parents=True)
    (folder / "metadata" / "seance.json").write_text(json.dumps([1, 2]), encoding="utf-8")

    with pytest.raises(SessionServiceError):
        read_metadata(folder)


def test_mark_audio_outputs_stale_flags_existing_artifacts(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    (folder / "transcript").mkdir(parents=True)
    (folder / "transcript" / "transcription.md").write_text("texte", encoding="utf-8")
    (folder / "summary").mkdir()
    (folder / "summary" / "resume_audio.md").write_text("résumé", encoding="utf-8")

    metadata: dict[str, Any] = {}
    mark_audio_outputs_stale(folder, metadata)

    assert metadata == {"audio_transcript_stale": True, "audio_summary_stale": True}


def test_mark_audio_outputs_stale_ignores_missing_artifacts(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    folder.mkdir()

    metadata: dict[str, Any] = {"title": "sans document"}
    mark_audio_outputs_stale(folder, metadata)

    assert metadata == {"title": "sans document"}


def test_mark_audio_outputs_stale_handles_each_artifact_separately(tmp_path: Path) -> None:
    folder = tmp_path / "session"
    (folder / "transcript").mkdir(parents=True)
    (folder / "transcript" / "transcription.md").write_text("texte", encoding="utf-8")

    metadata: dict[str, Any] = {}
    mark_audio_outputs_stale(folder, metadata)

    assert metadata == {"audio_transcript_stale": True}


class _Upload:
    def __init__(self, chunks: list[bytes], filename: str = "audio.wav") -> None:
        self.filename = filename
        self._chunks = list(chunks)
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    async def close(self) -> None:
        self.closed = True


class _FailingUpload(_Upload):
    async def read(self, size: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        raise OSError("flux interrompu")


def _run_import(upload: _Upload, settings_json: str = "{}") -> dict[str, Any]:
    return asyncio.run(web_app.import_and_process(upload, settings_json, "process", True, 30.0))


@pytest.fixture(autouse=True)
def _media_import_tools_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep import tests independent from FFmpeg being installed on the host."""
    monkeypatch.setattr(
        web_app, "ensure_media_toolchain_ready",
        lambda info, options=None, project_root=".": None,
    )


def _upload_files(root: Path) -> list[Path]:
    return list((root / "sessions" / ".web-uploads").iterdir())


def test_import_removes_temporary_file_when_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    upload = _FailingUpload([b"premier bloc"])

    with pytest.raises(OSError, match="flux interrompu"):
        _run_import(upload)

    assert upload.closed is True
    assert _upload_files(tmp_path) == []


def test_import_rejects_oversized_file_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    monkeypatch.setattr(web_app, "MAX_IMPORT_BYTES", 4)

    with pytest.raises(HTTPException) as error:
        _run_import(_Upload([b"12345"]))

    assert error.value.status_code == 413
    assert _upload_files(tmp_path) == []


def test_import_rejects_empty_file_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")

    with pytest.raises(HTTPException) as error:
        _run_import(_Upload([]))

    assert error.value.status_code == 400
    assert _upload_files(tmp_path) == []


def test_import_keeps_temporary_file_when_job_is_enqueued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    captured: dict[str, Any] = {}

    def fake_enqueue(
        kind: str, message: str, worker: Any, **kwargs: Any,
    ) -> dict[str, Any]:
        captured["payload"] = kwargs["payload"]
        return {"id": "job-1"}

    monkeypatch.setattr(web_app, "_enqueue_job", fake_enqueue)

    result = _run_import(_Upload([b"audio complet"]))

    assert result == {"id": "job-1"}
    source = Path(captured["payload"]["source_file"])
    assert source.is_file()
    assert source.read_bytes() == b"audio complet"


def test_import_removes_temporary_file_when_enqueue_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")

    def failing_enqueue(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status_code=409, detail="File occupée.")

    monkeypatch.setattr(web_app, "_enqueue_job", failing_enqueue)

    with pytest.raises(HTTPException) as error:
        _run_import(_Upload([b"audio complet"]))

    assert error.value.status_code == 409
    assert _upload_files(tmp_path) == []


def test_import_rejects_missing_media_tools_without_writing_the_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")

    def missing_tools(info: Any, options: Any = None, project_root: Any = ".") -> None:
        raise MediaToolchainUnavailable(f"ffprobe introuvable : « {options.get('ffprobe')} ».")

    monkeypatch.setattr(web_app, "ensure_media_toolchain_ready", missing_tools)

    with pytest.raises(HTTPException) as error:
        _run_import(_Upload([b"audio complet"]))

    assert error.value.status_code == 409
    assert "ffprobe introuvable" in error.value.detail
    assert not (tmp_path / "sessions" / ".web-uploads").exists()


def _deny_ffmpeg_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make FFmpeg/ffprobe unresolvable without touching the host."""
    monkeypatch.setattr(web_app, "ensure_media_toolchain_ready", ensure_media_toolchain_ready)
    monkeypatch.setattr(
        "seance.providers.media_tools.resolve_command",
        lambda value, default=None: None,
    )
    monkeypatch.setattr(
        "seance.providers.media_tools.resolve_ffprobe",
        lambda *_args, **_kwargs: None,
    )


def test_import_preflight_accepts_the_native_provider_without_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    _deny_ffmpeg_resolution(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_enqueue(kind: str, message: str, worker: Any, **kwargs: Any) -> dict[str, Any]:
        captured["payload"] = kwargs["payload"]
        return {"id": "job-1"}

    monkeypatch.setattr(web_app, "_enqueue_job", fake_enqueue)

    result = _run_import(_Upload([b"audio wav complet"]), '{"media_provider": "native"}')

    assert result == {"id": "job-1"}
    assert captured["payload"]["settings"]["media_provider"] == "native"


def test_import_preflight_rejects_ffmpeg_when_its_binaries_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    _deny_ffmpeg_resolution(monkeypatch)

    with pytest.raises(HTTPException) as error:
        _run_import(_Upload([b"audio complet"]))

    assert error.value.status_code == 409
    assert "FFmpeg introuvable" in error.value.detail
    assert not (tmp_path / "sessions" / ".web-uploads").exists()


def _seed_import_job(job_id: str, source: Path) -> None:
    payload = {
        "type": "import", "action": "process", "source_file": str(source),
        "display_name": source.name, "settings": {},
        "normalization": {"enabled": True, "max_gain_db": 30.0},
    }
    with web_app.STATE_LOCK:
        web_app.JOBS[job_id] = {
            "id": job_id, "kind": "import", "state": "queued", "phase": "queued",
            "message": "Import en préparation", "session_id": None,
            "created_at": "2026-01-01T10:00:00+00:00", "updated_at": "2026-01-01T10:00:00+00:00",
            "started_at": None, "finished_at": None, "error": None, "queue_position": 1,
            "_payload": payload,
        }


def _temporary_upload(tmp_path: Path) -> Path:
    source = tmp_path / "sessions" / ".web-uploads" / "import-test.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    return source


def test_import_job_removes_temporary_file_when_import_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    monkeypatch.setattr(web_app, "JOB_STORE", None)
    source = _temporary_upload(tmp_path)
    job_id = "import-failing"
    _seed_import_job(job_id, source)
    session_calls: list[Any] = []

    def failing_import(*args: Any, **kwargs: Any) -> Path:
        raise RuntimeError("FFmpeg introuvable : « ffmpeg ».")

    monkeypatch.setattr("seance.media.audio_import.import_audio_file", failing_import)
    monkeypatch.setattr(web_app, "_run_session_job", lambda *args: session_calls.append(args))

    try:
        with pytest.raises(RuntimeError, match="FFmpeg introuvable"):
            web_app._run_import_job(job_id)

        assert not source.exists()
        assert session_calls == []
        created = [entry for entry in (tmp_path / "sessions").iterdir() if entry.name != ".web-uploads"]
        assert created == []
    finally:
        with web_app.STATE_LOCK:
            web_app.JOBS.pop(job_id, None)


def test_import_job_removes_temporary_file_after_successful_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "SESSION_ROOT", tmp_path / "sessions")
    monkeypatch.setattr(web_app, "JOB_STORE", None)
    source = _temporary_upload(tmp_path)
    session_folder = tmp_path / "sessions" / "2026-01-01_10-00-00"
    session_folder.mkdir(parents=True)
    job_id = "import-succeeding"
    _seed_import_job(job_id, source)
    captured: dict[str, Any] = {}

    def fake_import(source_file: Path, directory: Path, **kwargs: Any) -> Path:
        captured["source_file"] = source_file
        captured["kwargs"] = kwargs
        return session_folder

    monkeypatch.setattr("seance.media.audio_import.import_audio_file", fake_import)
    monkeypatch.setattr(web_app, "_save_session_processing_settings", lambda folder, settings: {})
    monkeypatch.setattr(
        web_app, "_run_session_job",
        lambda action, folder, settings, job: captured.update(action=action, folder=folder),
    )

    try:
        web_app._run_import_job(job_id)

        assert captured["source_file"] == source
        assert captured["kwargs"]["ffmpeg"] == "ffmpeg"
        assert captured["kwargs"]["ffprobe"] == "ffprobe"
        assert captured["folder"] == session_folder
        assert not source.exists()
    finally:
        with web_app.STATE_LOCK:
            web_app.JOBS.pop(job_id, None)
