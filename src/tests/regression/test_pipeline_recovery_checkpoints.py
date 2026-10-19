from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web.app as web_app


class PipelineRecoveryCheckpointTests(unittest.TestCase):
    def _job(self, job_id: str, payload: dict) -> None:
        with web_app.STATE_LOCK:
            web_app.JOBS[job_id] = {
                "id": job_id, "kind": payload["action"], "state": "running", "phase": "summarizing",
                "message": "Reprise test", "session_id": "session-test", "created_at": "2026-10-17T10:00:00+00:00",
                "updated_at": "2026-10-17T10:00:00+00:00", "started_at": None, "finished_at": None,
                "error": None, "queue_position": None, "_payload": payload,
            }

    def tearDown(self) -> None:
        with web_app.STATE_LOCK:
            for job_id in ("recover-skip-whisper", "recover-interrupted-whisper"):
                web_app.JOBS.pop(job_id, None)

    def test_process_resume_after_transcription_skips_whisper_and_runs_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            payload = {"type": "session", "action": "process", "session_id": "session-test",
                       "settings": {}, "checkpoint": "transcribed", "resume_phase": "summarizing"}
            self._job("recover-skip-whisper", payload)
            with patch.object(web_app, "JOB_STORE", None), \
                 patch.object(web_app, "transcribe_folder") as transcribe, \
                 patch.object(web_app, "minutes_folder") as summarize:
                web_app._run_session_job("process", folder, web_app.Settings(), "recover-skip-whisper")
            transcribe.assert_not_called()
            summarize.assert_called_once()
            self.assertEqual(web_app.JOBS["recover-skip-whisper"]["_payload"]["checkpoint"], "summarized")

    def test_process_resume_during_whisper_repeats_whisper_even_if_partial_transcript_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "transcription.md").write_text("partial", encoding="utf-8")
            payload = {"type": "session", "action": "process", "session_id": "session-test",
                       "settings": {}, "checkpoint": None, "resume_phase": "transcribing"}
            self._job("recover-interrupted-whisper", payload)
            with patch.object(web_app, "JOB_STORE", None), \
                 patch.object(web_app, "get_transcript_path", return_value=folder / "transcription.md"), \
                 patch.object(web_app, "has_audio", return_value=True), \
                 patch.object(web_app, "transcribe_folder") as transcribe, \
                 patch.object(web_app, "minutes_folder") as summarize:
                web_app._run_session_job("process", folder, web_app.Settings(), "recover-interrupted-whisper")
            transcribe.assert_called_once()
            summarize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
