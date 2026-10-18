from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from web.project_paths import discover_project_root, resolve_session_root


class ProjectPathDiscoveryTests(unittest.TestCase):
    def make_src_layout(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
        (root / "seances").mkdir()
        (root / "models").mkdir()
        (root / "src" / "seance").mkdir(parents=True)
        app_file = root / "src" / "web" / "app.py"
        app_file.parent.mkdir(parents=True)
        app_file.write_text("# test app", encoding="utf-8")
        return app_file

    def test_finds_repository_root_when_launched_from_src(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            app_file = self.make_src_layout(root)
            self.assertEqual(
                discover_project_root(start_dir=root / "src", package_file=app_file),
                root.resolve(),
            )

    def test_finds_source_root_when_launched_from_an_unrelated_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "project"
            app_file = self.make_src_layout(root)
            unrelated = base / "elsewhere"
            unrelated.mkdir()
            self.assertEqual(
                discover_project_root(start_dir=unrelated, package_file=app_file),
                root.resolve(),
            )

    def test_explicit_project_root_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "chosen"
            root.mkdir()
            self.assertEqual(
                discover_project_root(start_dir=Path(temp), explicit_root=root),
                root.resolve(),
            )

    def test_glimio_project_root_takes_priority_over_legacy_environment_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            current = temp_path / "glimio-root"
            legacy = temp_path / "legacy-root"
            current.mkdir()
            legacy.mkdir()
            with patch.dict(os.environ, {
                "GLIMIO_PROJECT_ROOT": str(current),
                "SEANCE_PROJECT_ROOT": str(legacy),
            }):
                self.assertEqual(discover_project_root(start_dir=temp_path), current.resolve())

    def test_glimio_session_directory_takes_priority_over_legacy_environment_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch.dict(os.environ, {
                "GLIMIO_DIRECTORY": "glimio-sessions",
                "SEANCE_DIRECTORY": "legacy-sessions",
            }):
                self.assertEqual(
                    resolve_session_root(root, None),
                    (root / "glimio-sessions").resolve(),
                )

    def test_relative_session_directory_is_resolved_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.assertEqual(resolve_session_root(root, "seances"), (root / "seances").resolve())
            absolute = (root / "custom-sessions").resolve()
            self.assertEqual(resolve_session_root(root, absolute), absolute)

    def test_defaults_to_project_seances_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.assertEqual(resolve_session_root(root, None), (root / "seances").resolve())

    def test_timestamped_sessions_are_visible_under_the_resolved_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            app_file = self.make_src_layout(project)
            session = project / "seances" / "2026-10-17_11-20-57"
            (session / "summary").mkdir(parents=True)
            (session / "transcript").mkdir(parents=True)
            (session / "summary" / "resume_audio.md").write_text("Résumé", encoding="utf-8")
            (session / "transcript" / "transcription.md").write_text("Transcription", encoding="utf-8")

            discovered = discover_project_root(start_dir=project / "src", package_file=app_file)
            resolved_sessions = resolve_session_root(discovered)
            names = {path.name for path in resolved_sessions.iterdir() if path.is_dir()}

            self.assertEqual(resolved_sessions, (project / "seances").resolve())
            self.assertIn("2026-10-17_11-20-57", names)
            self.assertTrue((resolved_sessions / "2026-10-17_11-20-57" / "summary" / "resume_audio.md").is_file())


if __name__ == "__main__":
    unittest.main()
