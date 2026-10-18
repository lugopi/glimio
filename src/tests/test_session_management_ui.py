from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from web.app import RenameSessionRequest, delete_session, rename_session, sessions
from web.services.library import list_sessions_page
from seance.minutes import _maybe_generate_default_session_title


class LibraryPaginationTests(unittest.TestCase):
    def test_pages_return_only_requested_rows_and_global_total(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(35):
                folder = root / f"2026-10-17_00-{index:02d}-00"
                summary = folder / "summary" / "resume_audio.md"
                summary.parent.mkdir(parents=True)
                summary.write_text(f"Session topic number {index}", encoding="utf-8")

            items, total = list_sessions_page(root, limit=10, offset=20)

        self.assertEqual(total, 35)
        self.assertEqual(len(items), 10)
        self.assertEqual(items[0]["id"], "2026-10-17_00-14-00")
        self.assertEqual(items[-1]["id"], "2026-10-17_00-05-00")

    def test_web_pagination_endpoint_passes_offset_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(22):
                folder = root / f"2026-10-17_01-{index:02d}-00"
                folder.mkdir()
            with patch("web.app.SESSION_ROOT", root):
                payload = sessions(q="", filter_by="all", limit="10", offset=10)

        self.assertEqual(payload["count"], 22)
        self.assertEqual(payload["page_count"], 10)
        self.assertEqual(payload["offset"], 10)
        self.assertEqual(len(payload["items"]), 10)


class SessionMutationTests(unittest.TestCase):
    def make_session(self, root: Path, name: str = "2026-10-17_10-00-00") -> Path:
        folder = root / name
        metadata = folder / "metadata" / "seance.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(
            json.dumps({"title": "Session", "title_source": "default", "started_at": "2026-10-17T10:00:00+02:00"}),
            encoding="utf-8",
        )
        (folder / "summary").mkdir()
        (folder / "summary" / "resume_audio.md").write_text("Résumé de test", encoding="utf-8")
        return folder

    def test_rename_preserves_metadata_and_marks_title_as_user_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            with patch("web.app.SESSION_ROOT", root):
                response = rename_session(folder.name, RenameSessionRequest(title="Architecture audio"))
            metadata = json.loads((folder / "metadata" / "seance.json").read_text(encoding="utf-8"))

        self.assertEqual(response["title"], "Architecture audio")
        self.assertEqual(metadata["title_source"], "user")
        self.assertEqual(metadata["started_at"], "2026-10-17T10:00:00+02:00")

    def test_rename_rejects_blank_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            with patch("web.app.SESSION_ROOT", root):
                with self.assertRaises(HTTPException) as raised:
                    rename_session(folder.name, RenameSessionRequest(title="   "))
        self.assertEqual(raised.exception.status_code, 422)

    def test_rename_refuses_a_session_with_an_active_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            active_job = {
                "id": "job-1", "session_id": folder.name,
                "kind": "recording", "state": "running",
            }
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {"job-1": active_job}):
                with self.assertRaises(HTTPException) as raised:
                    rename_session(folder.name, RenameSessionRequest(title="Nouveau titre"))
                metadata = json.loads((folder / "metadata" / "seance.json").read_text(encoding="utf-8"))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(metadata["title"], "Session")

    def test_delete_removes_session_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {}):
                response = delete_session(folder.name)
        self.assertEqual(response, {"deleted": True, "id": folder.name})
        self.assertFalse(folder.exists())

    def test_delete_refuses_a_session_with_an_active_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            active_job = {
                "id": "job-1", "session_id": folder.name,
                "kind": "process", "state": "running",
            }
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {"job-1": active_job}):
                with self.assertRaises(HTTPException) as raised:
                    delete_session(folder.name)
                self.assertTrue(folder.exists())
        self.assertEqual(raised.exception.status_code, 409)

    def test_delete_refuses_a_session_while_its_job_is_queued(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            queued_job = {
                "id": "job-queued", "session_id": folder.name,
                "kind": "process", "state": "queued", "queue_position": 1,
            }
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {"job-queued": queued_job}):
                with self.assertRaises(HTTPException) as raised:
                    delete_session(folder.name)
                self.assertTrue(folder.exists())
        self.assertEqual(raised.exception.status_code, 409)

    def test_rename_refuses_a_session_while_its_job_is_queued(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = self.make_session(root)
            queued_job = {
                "id": "job-queued", "session_id": folder.name,
                "kind": "transcribe", "state": "queued", "queue_position": 1,
            }
            with patch("web.app.SESSION_ROOT", root), patch("web.app.JOBS", {"job-queued": queued_job}):
                with self.assertRaises(HTTPException) as raised:
                    rename_session(folder.name, RenameSessionRequest(title="Ne pas renommer pendant la file"))
        self.assertEqual(raised.exception.status_code, 409)


class AutomaticSessionTitleTests(unittest.TestCase):
    def test_default_title_is_replaced_and_trailing_letters_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "2026-10-17_10-00-00"
            metadata_path = folder / "metadata" / "seance.json"
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text(json.dumps({"title": "Session", "title_source": "default"}), encoding="utf-8")
            with patch("seance.minutes._run_llama_resilient", return_value=("Migration et test", False)):
                title = _maybe_generate_default_session_title(
                    folder, "Le système doit migrer vers une architecture plus simple.",
                    executable=Path("fake-llama.exe"), model_path=Path("fake-model.gguf"), context=8192,
                )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(title, "Migration et test")
        self.assertEqual(metadata["title"], "Migration et test")
        self.assertEqual(metadata["title_source"], "llm")

    def test_user_title_is_never_overwritten_by_auto_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "2026-10-17_10-00-00"
            metadata_path = folder / "metadata" / "seance.json"
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text(json.dumps({"title": "Mon titre", "title_source": "user"}), encoding="utf-8")
            with patch("seance.minutes._run_llama_resilient", side_effect=AssertionError("LLM must not run")):
                title = _maybe_generate_default_session_title(
                    folder, "Le résumé de séance.",
                    executable=Path("fake-llama.exe"), model_path=Path("fake-model.gguf"), context=8192,
                )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertIsNone(title)
        self.assertEqual(metadata["title"], "Mon titre")


class UIAvailabilityContractsTests(unittest.TestCase):
    def test_unavailable_document_tabs_are_hidden_instead_of_rendered_disabled(self) -> None:
        web = Path(__file__).resolve().parents[1] / "web"
        library_js = (web / "static" / "js" / "pages" / "library.js").read_text(encoding="utf-8")
        self.assertIn("session.summary ? '<button class=\"detail-tab", library_js)
        self.assertIn("session.transcript ? `<button class=\"detail-tab", library_js)
        self.assertEqual(library_js.count('data-doc="transcript"'), 1)
        self.assertNotIn("label: 'Transcription'", library_js)

    def test_recording_advanced_controls_are_conditional(self) -> None:
        web = Path(__file__).resolve().parents[1] / "web"
        recording_js = (web / "static" / "js" / "pages" / "recording.js").read_text(encoding="utf-8")
        html = (web / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("thresholdField.hidden", recording_js)
        self.assertNotIn("threshold.disabled = !automaticCount", recording_js)
        self.assertIn("its visibility and editability", recording_js)
        self.assertIn('id="diarization-num-speakers"', html)
        self.assertIn('id="diarization-threshold"', html)
        self.assertNotIn("Prêt à enregistrer", html)
        self.assertNotIn("accent-picker", html)


if __name__ == "__main__":
    unittest.main()
