from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from web.app import clear_job_history, delete_job_history_item, health, session_audio, sessions


class WebApiSmokeTests(unittest.TestCase):
    def test_sessions_endpoint_uses_configured_root_and_lists_existing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            summary = session / "summary" / "resume_audio.md"
            transcript = session / "transcript" / "transcription.md"
            summary.parent.mkdir(parents=True)
            transcript.parent.mkdir(parents=True)
            summary.write_text("# Un résumé\nUn sujet important.", encoding="utf-8")
            transcript.write_text("# Transcription\nUn sujet important.", encoding="utf-8")

            with patch("web.app.SESSION_ROOT", root), patch("web.app.PROJECT_ROOT", root.parent):
                payload = sessions(q="", filter_by="all", limit=250)
                status = health()

        self.assertEqual(payload["root"], str(root))
        self.assertTrue(payload["root_exists"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], session.name)
        self.assertTrue(payload["items"][0]["summary"])
        self.assertTrue(payload["items"][0]["transcript"])
        self.assertEqual(status["session_root"], str(root))
        self.assertTrue(status["session_root_exists"])


    def test_audio_endpoint_does_not_serve_a_wav_while_recording_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            audio = session / "audio" / "windows.wav"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"still-being-written")
            request = Request({
                "type": "http", "http_version": "1.1", "method": "GET",
                "scheme": "http", "path": "/api/sessions/2026-10-17_10-30-00/audio/windows.wav",
                "raw_path": b"/api/sessions/2026-10-17_10-30-00/audio/windows.wav",
                "query_string": b"", "headers": [], "server": ("127.0.0.1", 8765),
                "client": ("127.0.0.1", 12345),
            })
            active_job = {
                "kind": "recording", "session_id": session.name,
                "state": "running", "phase": "recording",
            }
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {"job-1": active_job}):
                with self.assertRaises(HTTPException) as raised:
                    session_audio(session.name, "windows.wav", request)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("finalisation", str(raised.exception.detail))



    def test_delete_one_finished_activity_and_reject_running_activity(self) -> None:
        import web.app as web_app
        records = {
            "done": {"id": "done", "state": "completed"},
            "running": {"id": "running", "state": "running"},
        }
        with patch("web.app._initialize_persistence"), \
             patch("web.app.JOBS", records), \
             patch("web.app.STOP_EVENTS", {}), \
             patch("web.app.PROCESSING_QUEUE_IDS", []), \
             patch("web.app.ACTIVE_JOB_ID", "running"), \
             patch("web.app.PROCESSING_JOB_ID", None), \
             patch("web.app.JOB_STORE", None):
            self.assertEqual(delete_job_history_item("done"), {"deleted": "done"})
            self.assertNotIn("done", web_app.JOBS)
            with self.assertRaises(HTTPException) as raised:
                delete_job_history_item("running")
            self.assertEqual(raised.exception.status_code, 409)
            with self.assertRaises(HTTPException) as missing:
                delete_job_history_item("missing")
            self.assertEqual(missing.exception.status_code, 404)

    def test_clear_job_history_keeps_running_and_queued_jobs(self) -> None:
        import web.app as web_app
        records = {
            "done": {"id": "done", "state": "completed"},
            "failed": {"id": "failed", "state": "error"},
            "running": {"id": "running", "state": "running"},
            "queued": {"id": "queued", "state": "queued"},
        }
        with patch("web.app._initialize_persistence"), \
             patch("web.app.JOBS", records), \
             patch("web.app.STOP_EVENTS", {}), \
             patch("web.app.PROCESSING_QUEUE_IDS", ["queued"]), \
             patch("web.app.ACTIVE_JOB_ID", "running"), \
             patch("web.app.PROCESSING_JOB_ID", None), \
             patch("web.app.JOB_STORE", None):
            result = clear_job_history()
            self.assertEqual(result, {"deleted": 2})
            self.assertEqual(set(web_app.JOBS), {"running", "queued"})


if __name__ == "__main__":
    unittest.main()
