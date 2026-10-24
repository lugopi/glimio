from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Response
from starlette.requests import Request

from web.app import (AudioTrackToggleRequest, AudioDevicesResponse, SaveSummaryRequest, _artifact_tail_hash, clear_job_history, delete_job_history_item, devices, health, save_session_summary, session_audio, session_artifact, sessions, set_session_audio_track_disabled, delete_session_audio_track)


class WebApiSmokeTests(unittest.TestCase):
    def test_devices_response_schema_accepts_structured_device_records(self) -> None:
        payload = {
            "microphones": ["USB Microphone"],
            "outputs": ["Speakers"],
            "microphone_devices": [{"id": "mic-1", "key": "mic-1", "name": "USB Microphone"}],
            "output_devices": [{"id": "out-1", "key": "out-1", "name": "Speakers"}],
        }
        with patch("web.app._device_names", return_value=payload):
            result = devices()
        self.assertIsInstance(result, AudioDevicesResponse)
        self.assertEqual(result.microphones, ["USB Microphone"])
        self.assertEqual(result.output_devices[0].id, "out-1")
        self.assertEqual(result.output_devices[0].name, "Speakers")

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


    def test_soft_disable_cannot_disable_the_last_active_audio_track(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            (session / "audio").mkdir(parents=True)
            (session / "audio" / "micro.wav").write_bytes(b"wav")
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {}):
                with self.assertRaises(HTTPException) as raised:
                    set_session_audio_track_disabled(session.name, "micro.wav", AudioTrackToggleRequest(disabled=True))
            self.assertEqual(raised.exception.status_code, 422)
            self.assertIn("Au moins une piste audio", str(raised.exception.detail))
            self.assertTrue((session / "audio" / "micro.wav").is_file())

    def test_soft_disable_marks_existing_artifacts_stale_and_preserves_audio(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            (session / "audio").mkdir(parents=True)
            (session / "transcript").mkdir()
            (session / "summary").mkdir()
            (session / "audio" / "micro.wav").write_bytes(b"wav1")
            (session / "audio" / "windows.wav").write_bytes(b"wav2")
            (session / "transcript" / "transcription.md").write_text("# Transcript", encoding="utf-8")
            (session / "summary" / "resume_audio.md").write_text("# Summary", encoding="utf-8")
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {}):
                result = set_session_audio_track_disabled(session.name, "micro.wav", AudioTrackToggleRequest(disabled=True))
            self.assertEqual(result["disabled_audio_tracks"], ["micro.wav"])
            self.assertTrue(result["metadata"]["audio_transcript_stale"])
            self.assertTrue(result["metadata"]["audio_summary_stale"])
            self.assertTrue((session / "audio" / "micro.wav").is_file())

    def test_hard_delete_removes_one_track_and_marks_combined_artifacts_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            (session / "audio").mkdir(parents=True)
            (session / "transcript").mkdir()
            (session / "summary").mkdir()
            (session / "audio" / "micro.wav").write_bytes(b"wav1")
            (session / "audio" / "windows.wav").write_bytes(b"wav2")
            (session / "transcript" / "micro.srt").write_text("track text", encoding="utf-8")
            (session / "transcript" / "transcription.md").write_text("# Transcript", encoding="utf-8")
            (session / "summary" / "resume_audio.md").write_text("# Summary", encoding="utf-8")
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {}):
                result = delete_session_audio_track(session.name, "micro.wav")
            self.assertEqual(result["audio_tracks"], ["windows.wav"])
            self.assertFalse((session / "audio" / "micro.wav").exists())
            self.assertFalse((session / "transcript" / "micro.srt").exists())
            self.assertTrue(result["metadata"]["audio_transcript_stale"])
            self.assertTrue(result["metadata"]["audio_summary_stale"])

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

    def _live_transcript_session(self, temp_dir: str, content: str) -> tuple[Path, Path]:
        root = Path(temp_dir) / "seances"
        session = root / "2026-10-17_10-30-00"
        live = session / "transcript" / "transcription_en_cours.md"
        live.parent.mkdir(parents=True)
        live.write_text(content, encoding="utf-8")
        return root, live

    def test_save_session_summary_persists_markdown_and_returns_new_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            summary = session / "summary" / "resume_audio.md"
            summary.parent.mkdir(parents=True)
            summary.write_text("# Avant\n", encoding="utf-8")
            stat = summary.stat()
            revision = f"{stat.st_mtime_ns}:{stat.st_size}"
            content = "# Après\n\n- Décision\n- Action"

            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {}):
                result = save_session_summary(session.name, SaveSummaryRequest(content=content, revision=revision))

            self.assertEqual(summary.read_text(encoding="utf-8"), content)
            self.assertEqual(result["content"], content)
            self.assertEqual(result["kind"], "summary")
            self.assertEqual(result["filename"], "resume_audio.md")
            self.assertEqual(result["revision"], f"{summary.stat().st_mtime_ns}:{summary.stat().st_size}")

    def test_save_session_summary_rejects_stale_revision_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            summary = session / "summary" / "resume_audio.md"
            summary.parent.mkdir(parents=True)
            summary.write_text("# Version initiale", encoding="utf-8")
            stat = summary.stat()
            stale_revision = f"{stat.st_mtime_ns}:{stat.st_size}"
            summary.write_text("# Modification externe plus longue", encoding="utf-8")

            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {}):
                with self.assertRaises(HTTPException) as raised:
                    save_session_summary(session.name, SaveSummaryRequest(content="# Mon édition", revision=stale_revision))

            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(summary.read_text(encoding="utf-8"), "# Modification externe plus longue")

    def test_save_session_summary_rejects_active_processing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            summary = session / "summary" / "resume_audio.md"
            summary.parent.mkdir(parents=True)
            summary.write_text("# Résumé", encoding="utf-8")
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {
                "job-1": {"id": "job-1", "session_id": session.name, "state": "running", "kind": "process"}
            }):
                with self.assertRaises(HTTPException) as raised:
                    save_session_summary(session.name, SaveSummaryRequest(content="# Édition"))
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(summary.read_text(encoding="utf-8"), "# Résumé")

    def test_session_artifact_returns_live_content_and_full_document_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, live = self._live_transcript_session(temp_dir, "Bonjour le monde")
            response = Response()
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                result = session_artifact(live.parent.parent.name, "transcript", response)

            self.assertTrue(result["live"])
            self.assertEqual(result["content"], "Bonjour le monde")
            self.assertFalse(result["append"])
            self.assertFalse(result["unchanged"])

            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                unchanged = session_artifact(
                    live.parent.parent.name, "transcript", Response(), revision=result["revision"],
                )

            self.assertTrue(unchanged["unchanged"])
            self.assertTrue(unchanged["live"])
            self.assertNotIn("content", unchanged)

    def test_session_artifact_appends_with_matching_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, live = self._live_transcript_session(temp_dir, "Bonjour le monde")
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                result = session_artifact(
                    live.parent.parent.name, "transcript", Response(),
                    offset=len("Bonjour"), tail_hash=_artifact_tail_hash("Bonjour"),
                )

            self.assertTrue(result["append"])
            self.assertEqual(result["content"], " le monde")
            self.assertTrue(result["live"])

    def test_session_artifact_hashes_unicode_tail_by_code_point(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, live = self._live_transcript_session(temp_dir, "a😀b suite")
            content = "a😀b suite"
            offset = 3
            self.assertEqual(content[:offset], "a😀b")
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                result = session_artifact(
                    live.parent.parent.name, "transcript", Response(),
                    offset=offset, tail_hash=_artifact_tail_hash(content[:offset]),
                )

            self.assertTrue(result["append"])
            self.assertEqual(result["content"], " suite")

    def test_artifact_tail_hash_vectors(self) -> None:
        self.assertEqual(_artifact_tail_hash("abc"), "1a47e90b")
        self.assertEqual(_artifact_tail_hash("a😀b"), "4e6351d2")

    def test_session_artifact_replaces_content_when_tail_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, live = self._live_transcript_session(temp_dir, "Bonjour le monde")
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                result = session_artifact(
                    live.parent.parent.name, "transcript", Response(),
                    offset=len("Bonjour"), tail_hash=_artifact_tail_hash("Autre texte"),
                )

            self.assertFalse(result["append"])
            self.assertEqual(result["content"], "Bonjour le monde")

    def test_session_artifact_keeps_offset_only_append_for_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, live = self._live_transcript_session(temp_dir, "Bonjour le monde")
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                result = session_artifact(
                    live.parent.parent.name, "transcript", Response(), offset=len("Bonjour"),
                )

            self.assertTrue(result["append"])
            self.assertEqual(result["content"], " le monde")

    def test_session_artifact_reports_a_final_document_as_not_live(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            final = session / "transcript" / "transcription.md"
            final.parent.mkdir(parents=True)
            final.write_text("Document final", encoding="utf-8")
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value=None):
                result = session_artifact(session.name, "transcript", Response())

            self.assertFalse(result["live"])
            self.assertEqual(result["content"], "Document final")
            self.assertFalse(result["append"])

    def test_session_artifact_reports_pending_without_a_live_file_as_not_live(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "seances"
            session = root / "2026-10-17_10-30-00"
            (session / "transcript").mkdir(parents=True)
            with patch("web.app.SESSION_ROOT", root), \
                 patch("web.app._active_session_artifact_job", return_value={"id": "job-1"}):
                result = session_artifact(session.name, "transcript", Response())

            self.assertTrue(result["pending"])
            self.assertFalse(result["live"])
            self.assertEqual(result["content"], "")


if __name__ == "__main__":
    unittest.main()
