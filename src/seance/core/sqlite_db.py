"""Shared SQLite connection and schema lifecycle for Glimio persistence."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager


def database_path(project_root: str | Path) -> Path:
    """Return the stable local database path, with an override for portable installs."""
    override = os.environ.get("GLIMIO_DATA_DIR", "").strip()
    data_dir = Path(override).expanduser() if override else Path(project_root) / ".glimio"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "glimio.sqlite3"


class SQLiteDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            # FULL favors durability across OS/power failures; queue/preferences writes
            # are small and reliability matters more than marginal write throughput.
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    message TEXT NOT NULL,
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT,
                    queue_position INTEGER,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_state_created ON jobs(state, created_at)")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=30, isolation_level="DEFERRED")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        # synchronous is connection-local in SQLite, so enforce durability on every connection.
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
