from __future__ import annotations

import json
from pathlib import Path

import web.app as web_app
from web.app import SessionSettingsRequest, Settings, save_session_settings


def test_session_processing_settings_are_persisted_without_losing_metadata(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "sessions"
    folder = root / "2026-10-18_12-30-00"
    metadata_path = folder / "metadata" / "seance.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(json.dumps({"title": "Point projet", "title_source": "user"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "SESSION_ROOT", root)

    result = save_session_settings(folder.name, SessionSettingsRequest(settings=Settings(
        language="fr", diarize=True, diarization_num_speakers=3, format="technical",
    )))

    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert result["id"] == folder.name
    assert saved["title"] == "Point projet"
    assert saved["title_source"] == "user"
    assert saved["processing_settings"]["language"] == "fr"
    assert saved["processing_settings"]["diarize"] is True
    assert saved["processing_settings"]["diarization_num_speakers"] == 3
    assert saved["processing_settings"]["format"] == "technical"
