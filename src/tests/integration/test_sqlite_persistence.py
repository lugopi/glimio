from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seance.core.job_store import JobStore
from seance.core.preferences_store import PreferencesStore
from seance.core.sqlite_db import SQLiteDatabase


class SQLitePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "glimio.sqlite3"
        self.database = SQLiteDatabase(self.path)
        self.database.initialize()
        self.jobs = JobStore(self.database)
        self.preferences = PreferencesStore(self.database)

    def test_database_connections_use_full_sync_for_power_loss_durability(self) -> None:
        with self.database.connect() as connection:
            mode = connection.execute("PRAGMA synchronous").fetchone()[0]
        self.assertEqual(mode, 2)  # SQLite FULL

    def test_preferences_survive_reopening_the_database(self) -> None:
        saved = {
            "settings": {"model": "models/asr/custom.bin", "threads": 6, "diarization_num_speakers": 4},
            "ui": {"theme": "dark", "capture_windows": False, "recording_workflow": "transcribe"},
        }
        self.preferences.save(saved)
        reopened = PreferencesStore(SQLiteDatabase(self.path))
        self.assertEqual(reopened.get(), saved)

    def test_job_state_and_resume_checkpoint_survive_reopening(self) -> None:
        job = {
            "id": "job-resume-001", "kind": "process", "state": "running",
            "phase": "summarizing", "message": "LLM · rédaction…", "session_id": "session-001",
            "created_at": "2026-10-17T10:00:00+00:00", "updated_at": "2026-10-17T10:02:00+00:00",
            "started_at": "2026-10-17T10:00:01+00:00", "finished_at": None,
            "error": None, "queue_position": None,
            "_payload": {"type": "session", "action": "process", "settings": {"threads": 4},
                         "checkpoint": "transcribed"},
        }
        self.jobs.save(job)
        reopened = JobStore(SQLiteDatabase(self.path)).load_recent()
        self.assertEqual(len(reopened), 1)
        self.assertEqual(reopened[0]["state"], "running")
        self.assertEqual(reopened[0]["_payload"]["checkpoint"], "transcribed")
        self.assertEqual(reopened[0]["_payload"]["settings"]["threads"], 4)

    def test_job_upsert_updates_state_and_checkpoint_without_duplicating(self) -> None:
        job = {
            "id": "job-001", "kind": "transcribe", "state": "queued", "phase": "queued",
            "message": "queued", "session_id": "s1", "created_at": "2026-10-17T10:00:00+00:00",
            "updated_at": "2026-10-17T10:00:00+00:00", "started_at": None, "finished_at": None,
            "error": None, "queue_position": 1,
            "_payload": {"type": "session", "action": "transcribe", "settings": {}, "checkpoint": None},
        }
        self.jobs.save(job)
        job.update({"state": "running", "phase": "transcribing", "queue_position": None,
                    "_payload": {"type": "session", "action": "transcribe", "settings": {}, "checkpoint": "transcribed"}})
        self.jobs.save(job)
        restored = self.jobs.load_recent()
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["state"], "running")
        self.assertEqual(restored[0]["_payload"]["checkpoint"], "transcribed")

    def test_fifo_order_is_stable_when_jobs_share_the_same_timestamp(self) -> None:
        created_at = "2026-10-17T10:00:00+00:00"
        for job_id in ("job-first", "job-second", "job-third"):
            self.jobs.save({
                "id": job_id, "kind": "transcribe", "state": "queued", "phase": "queued",
                "message": "queued", "session_id": "s1", "created_at": created_at,
                "updated_at": created_at, "started_at": None, "finished_at": None,
                "error": None, "queue_position": 1,
                "_payload": {"type": "session", "action": "transcribe", "settings": {}},
            })
        restored_ids = [job["id"] for job in self.jobs.load_recent()]
        self.assertEqual(restored_ids, ["job-first", "job-second", "job-third"])

    def test_startup_restores_interrupted_processing_to_fifo_queue(self) -> None:
        import queue
        from unittest.mock import patch
        import web.app as web_app

        job = {
            "id": "job-recover", "kind": "process", "state": "running", "phase": "summarizing",
            "message": "LLM en cours", "session_id": "session-recover",
            "created_at": "2026-10-17T10:00:00+00:00", "updated_at": "2026-10-17T10:02:00+00:00",
            "started_at": "2026-10-17T10:00:01+00:00", "finished_at": None,
            "error": None, "queue_position": None,
            "_payload": {"type": "session", "action": "process", "session_id": "session-recover",
                         "settings": {}, "checkpoint": "transcribed"},
        }
        self.jobs.save(job)
        with patch.object(web_app, "JOB_STORE", self.jobs), \
             patch.object(web_app, "PROCESSING_QUEUE", queue.Queue()), \
             patch.object(web_app, "PROCESSING_QUEUE_IDS", []), \
             patch.object(web_app, "JOBS", {}), \
             patch.object(web_app, "PERSISTENCE_RESTORED", False), \
             patch.object(web_app, "ACTIVE_JOB_ID", None), \
             patch.object(web_app, "_ensure_processing_worker"):
            web_app._restore_persisted_jobs()
            restored = web_app.JOBS["job-recover"]
            self.assertEqual(restored["state"], "queued")
            self.assertEqual(restored["_payload"]["checkpoint"], "transcribed")
            self.assertEqual(restored["_payload"]["resume_phase"], "summarizing")
            queued_id, worker = web_app.PROCESSING_QUEUE.get_nowait()
            self.assertEqual(queued_id, "job-recover")
            self.assertTrue(callable(worker))



if __name__ == "__main__":
    unittest.main()
