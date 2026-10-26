from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import patch

from seance.cli import build_parser
from seance.cli_commands import run_application_cli_command
from seance.core.job_store import JobStore
from seance.core.preferences_store import PreferencesStore
from seance.core.sqlite_db import SQLiteDatabase, database_path


def _make_session(root: Path, session_id: str = "2026-10-24_12-00-00") -> Path:
    folder = root / session_id
    (folder / "audio").mkdir(parents=True)
    (folder / "transcript").mkdir()
    (folder / "summary").mkdir()
    with wave.open(str(folder / "audio" / "audio_import.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 160)
    (folder / "transcript" / "transcription.md").write_text(
        "# Transcription\n\nDécision : préparer le lancement du projet.\n", encoding="utf-8"
    )
    (folder / "summary" / "resume_audio.md").write_text(
        "# Résumé\n\nLa décision concerne le lancement du projet.\n", encoding="utf-8"
    )
    (folder / "metadata").mkdir()
    (folder / "metadata" / "seance.json").write_text(
        json.dumps({"title": "Réunion de test", "processing_settings": {"language": "fr"}}),
        encoding="utf-8",
    )
    return folder


def _run(argv: list[str], project_root: Path) -> int | None:
    args = build_parser().parse_args(argv)
    return run_application_cli_command(args, project_root=project_root)


def test_cli_exposes_the_new_generic_summary_formats() -> None:
    parser = build_parser()
    for report_format in ("narrative", "dialogue", "learning", "daily", "technical", "formal", "brainstorm"):
        args = parser.parse_args(["summarize", "--format", report_format])
        assert args.format == report_format


def test_cli_has_library_jobs_preferences_search_and_devices_commands() -> None:
    parser = build_parser()
    for command_line in (
        ["sessions", "list"], ["sessions", "show", "id"], ["sessions", "rename", "id", "Title"],
        ["sessions", "audio", "list", "id"], ["sessions", "settings", "show", "id"],
        ["artifacts", "show", "id", "summary"], ["preferences", "show"], ["jobs", "list"],
        ["devices"], ["search", "project launch"], ["search", "--list"], ["search", "--synthesize", "id", "--excerpts", "1,2"],
    ):
        assert parser.parse_args(command_line).command in {
            "sessions", "session", "artifacts", "preferences", "prefs", "jobs", "devices", "search"
        }


def test_cli_sessions_shared_operations_and_search_history(tmp_path: Path, capsys) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    folder = _make_session(root)
    data_dir = tmp_path / "data"
    with patch.dict(os.environ, {"GLIMIO_DATA_DIR": str(data_dir)}):
        assert _run(["sessions", "list", "--directory", str(root), "--query", "lancement"], tmp_path) == 0
        output = capsys.readouterr().out
        assert "Réunion de test" in output

        assert _run(["sessions", "show", folder.name, "--directory", str(root), "--json"], tmp_path) == 0
        detail = json.loads(capsys.readouterr().out)
        assert detail["processing_settings"]["language"] == "fr"

        assert _run(["sessions", "rename", folder.name, "Projet renommé", "--directory", str(root)], tmp_path) == 0
        metadata = json.loads((folder / "metadata" / "seance.json").read_text(encoding="utf-8"))
        assert metadata["title"] == "Projet renommé"

        assert _run(["sessions", "audio", "disable", folder.name, "audio_import.wav", "--directory", str(root)], tmp_path) == 2
        err = capsys.readouterr().err
        assert "Au moins une piste audio" in err

        assert _run(["search", "lancement projet", "--directory", str(root), "--json"], tmp_path) == 0
        search_payload = json.loads(capsys.readouterr().out)
        assert search_payload["passages"]
        search_id = search_payload["id"]
        assert _run(["search", "--show", search_id, "--json"], tmp_path) == 0
        shown = json.loads(capsys.readouterr().out)
        assert shown["query"] == "lancement projet"


def test_cli_preferences_are_shared_with_web_persistence(tmp_path: Path, capsys) -> None:
    config = tmp_path / "prefs.json"
    config.write_text(json.dumps({"settings": {"language": "fr"}, "ui": {"theme": "dark"}}), encoding="utf-8")
    with patch.dict(os.environ, {"GLIMIO_DATA_DIR": str(tmp_path / "data")}):
        assert _run(["preferences", "save", "--file", str(config)], tmp_path) == 0
        database = SQLiteDatabase(database_path(tmp_path))
        database.initialize()
        stored = PreferencesStore(database).get()
        assert stored == {"settings": {"language": "fr"}, "ui": {"theme": "dark"}}
        capsys.readouterr()  # discard the save confirmation
        assert _run(["preferences", "show", "--json"], tmp_path) == 0
        assert json.loads(capsys.readouterr().out) == stored


def test_cli_does_not_import_web_frameworks() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run(
        [sys.executable, "-c", "import sys, seance.cli; assert 'fastapi' not in sys.modules; assert 'uvicorn' not in sys.modules"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
