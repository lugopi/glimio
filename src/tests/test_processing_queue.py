from __future__ import annotations

import re
import threading
import time
import unittest
from pathlib import Path

from web.app import _enqueue_job, _get_job_or_404, _start_job


class SerialProcessingQueueTests(unittest.TestCase):
    def test_processing_state_does_not_hide_or_lock_the_record_button(self) -> None:
        # Full Angular : le contrat est vérifié sur la page recording (le bouton
        # « Démarrer l'enregistrement » n'est jamais lié à un job de traitement).
        app = Path(__file__).resolve().parents[1] / "web" / "frontend" / "src" / "app"
        html = (app / "pages" / "recording" / "recording.page.html").read_text(encoding="utf-8")
        ts = (app / "pages" / "recording" / "recording.page.ts").read_text(encoding="utf-8")
        self.assertIn("Démarrer l'enregistrement", html)
        start_btn = re.search(r'\[disabled\]="([^"]*)"[^>]*\(click\)="startRecording', html)
        self.assertIsNotNone(start_btn, "Missing startRecording button")
        for forbidden in ("processingJob", "activeJob"):
            self.assertNotIn(forbidden, start_btn.group(1), f"Start button locked by {forbidden}")
        self.assertIn("activeRecording", ts)  # seul l'état d'enregistrement actif pilote la UI

    def test_jobs_run_fifo_and_only_one_processing_worker_runs_at_a_time(self) -> None:
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        second_finished = threading.Event()
        recording_finished = threading.Event()
        order: list[str] = []
        active = 0
        max_active = 0
        lock = threading.Lock()

        def first_worker(_job_id: str) -> None:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                order.append("first")
            first_started.set()
            if not release_first.wait(4):
                raise AssertionError("test did not release the first queue job")
            with lock:
                active -= 1

        def second_worker(_job_id: str) -> None:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                order.append("second")
            second_started.set()
            with lock:
                active -= 1
            second_finished.set()

        first = _enqueue_job("process", "first test job", first_worker, session_id="test-first")
        self.assertTrue(first_started.wait(2), "first job should start")
        second = _enqueue_job("transcribe", "second test job", second_worker, session_id="test-second")
        queued = _get_job_or_404(second["id"])
        self.assertEqual(queued["state"], "queued")
        self.assertEqual(queued["queue_position"], 1)
        self.assertFalse(second_started.wait(0.15), "second job must wait for the first")

        # The exclusive recording thread remains available even while the model queue is busy.
        recording = _start_job(
            "recording", "dummy capture", lambda _job_id: recording_finished.set()
        )
        self.assertTrue(recording_finished.wait(2), "recording must be allowed during model processing")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and _get_job_or_404(recording["id"])["state"] != "completed":
            time.sleep(0.01)
        self.assertEqual(_get_job_or_404(recording["id"])["state"], "completed")

        release_first.set()
        self.assertTrue(second_finished.wait(3), "second job should start after first finishes")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            first_state = _get_job_or_404(first["id"])["state"]
            second_state = _get_job_or_404(second["id"])["state"]
            if first_state == "completed" and second_state == "completed":
                break
            time.sleep(0.01)

        self.assertEqual(order, ["first", "second"])
        self.assertEqual(max_active, 1)
        self.assertEqual(_get_job_or_404(first["id"])["state"], "completed")
        self.assertEqual(_get_job_or_404(second["id"])["state"], "completed")


if __name__ == "__main__":
    unittest.main()
