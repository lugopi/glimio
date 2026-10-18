"""SQLite persistence for user preferences; no UI or request logic lives here."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .sqlite_db import SQLiteDatabase


class PreferencesStore:
    KEY = "app_preferences"

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def get(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM preferences WHERE key = ?", (self.KEY,)
            ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def save(self, value: dict[str, Any]) -> None:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO preferences(key, value_json, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                (self.KEY, serialized, now),
            )
