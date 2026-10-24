"""Durable job history and queue records backed by SQLite."""
from __future__ import annotations

import json
from typing import Any

from .sqlite_db import SQLiteDatabase


class JobStore:
    COLUMNS = (
        "id", "kind", "state", "phase", "message", "session_id", "created_at",
        "updated_at", "started_at", "finished_at", "error", "queue_position",
    )

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def save(self, job: dict[str, Any]) -> None:
        payload = job.get("_payload") or {}
        values = [job.get(column) for column in self.COLUMNS]
        values.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        placeholders = ",".join("?" for _ in range(len(self.COLUMNS) + 1))
        assignments = ",".join(f"{column}=excluded.{column}" for column in self.COLUMNS if column != "id")
        assignments += ",payload_json=excluded.payload_json"
        # Keep SQL composition explicit and all user data parameterized.
        sql = f"INSERT INTO jobs({','.join(self.COLUMNS)},payload_json) VALUES({placeholders}) ON CONFLICT(id) DO UPDATE SET {assignments}"
        with self.database.connect() as connection:
            connection.execute(sql, values)

    def delete(self, job_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def load_recent(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (max(1, min(5000, limit)),)
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = {column: row[column] for column in self.COLUMNS}
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
            item["_payload"] = payload if isinstance(payload, dict) else {}
            result.append(item)
        # The API / worker uses insertion order as a stable in-memory history ordering.
        result.reverse()
        return result

    def trim(self, keep: int = 1000) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                (max(100, keep),),
            )
