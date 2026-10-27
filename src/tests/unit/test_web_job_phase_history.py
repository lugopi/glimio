from __future__ import annotations

from unittest.mock import patch

import web.app as web_app
from web.app import _decorate_session_processing, _transition_job_phase_locked


def test_phase_transition_records_duration_and_starts_next_phase() -> None:
    job = {
        "phase": "transcribing",
        "phase_started_at": "2026-10-27T10:00:00+00:00",
        "phase_history": [{"phase": "starting", "duration_seconds": 2.0}],
    }

    with patch("web.app._now", return_value="2026-10-27T10:00:20+00:00"):
        _transition_job_phase_locked(job, "summarizing")

    assert job["phase"] == "summarizing"
    assert job["phase_started_at"] == "2026-10-27T10:00:20+00:00"
    assert job["phase_history"][-1] == {"phase": "transcribing", "duration_seconds": 20.0}


def test_terminal_transition_closes_final_phase_without_open_timer() -> None:
    job = {
        "phase": "summarizing",
        "phase_started_at": "2026-10-27T10:00:20+00:00",
        "phase_history": [],
    }

    with patch("web.app._now", return_value="2026-10-27T10:01:00+00:00"):
        _transition_job_phase_locked(job, "completed")

    assert job["phase"] == "completed"
    assert job["phase_started_at"] is None
    assert job["phase_history"] == [{"phase": "summarizing", "duration_seconds": 40.0}]


def test_republishing_same_phase_does_not_reset_elapsed_time() -> None:
    job = {
        "phase": "transcribing",
        "phase_started_at": "2026-10-27T10:00:00+00:00",
        "phase_history": [],
    }

    with patch("web.app._now") as clock:
        _transition_job_phase_locked(job, "transcribing")

    clock.assert_not_called()
    assert job["phase_started_at"] == "2026-10-27T10:00:00+00:00"
    assert job["phase_history"] == []


def test_session_processing_api_includes_phase_timing_for_live_eta() -> None:
    job = {
        "id": "live-job",
        "kind": "process",
        "state": "running",
        "phase": "summarizing",
        "session_id": "session-1",
        "created_at": "2026-10-27T10:00:00+00:00",
        "updated_at": "2026-10-27T10:01:00+00:00",
        "started_at": "2026-10-27T10:00:00+00:00",
        "phase_started_at": "2026-10-27T10:00:40+00:00",
        "phase_history": [{"phase": "transcribing", "duration_seconds": 40.0}],
        "finished_at": None,
    }

    with patch.dict(web_app.JOBS, {"live-job": job}, clear=True):
        result = _decorate_session_processing({"id": "session-1"})["processing"]

    assert result["phase_started_at"] == job["phase_started_at"]
    assert result["phase_history"] == job["phase_history"]
