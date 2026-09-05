"""Small SQLite persistence service for demurrage watchlist records."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.schemas import ContainerStatusResponse


class WatchlistService:
    """Persist watchlist rows in a local SQLite database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        configured_path = db_path or os.getenv("WATCHLIST_DB_PATH", "data/portalconnect.db")
        self.db_path = Path(configured_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_containers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    container_id TEXT NOT NULL UNIQUE,
                    terminal_id TEXT NOT NULL,
                    last_free_day TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fees_due REAL NOT NULL,
                    last_polled_at TEXT NOT NULL
                )
                """
            )
            existing = {row[1] for row in connection.execute("PRAGMA table_info(watchlist_containers)")}
            for name, definition in {
                "holds": "INTEGER NOT NULL DEFAULT 0",
                "urgency_level": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "notes": "TEXT NOT NULL DEFAULT ''",
                "pinned_at": "TEXT NOT NULL DEFAULT ''",
                "alert_sent_at": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE watchlist_containers ADD COLUMN {name} {definition}")

    def seed_demo_units(self) -> int:
        """Seed the standard fleet once, without overwriting real records."""

        seeds = [
            ("WFHU5080179", "LA_PIER_400", "AVAILABLE", 0.0, "2026-09-06", "CAUTION", "APM / PIER 400"),
            ("CMAU4928104", "NY_RED_HOOK", "DEMURRAGE_ACCRUING", 300.0, "2026-09-03", "CRITICAL", "RED HOOK / PIER 7"),
            ("FMSU1092834", "FENIX_PIER_300", "PENDING_TERMINAL_ADAPTER", 0.0, "2026-09-08", "SAFE", "FENIX / PIER 300"),
        ]
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM watchlist_containers").fetchone()[0]
            if count:
                return 0
            connection.executemany(
                "INSERT INTO watchlist_containers (container_id, terminal_id, last_free_day, status, fees_due, last_polled_at, holds, urgency_level, notes, pinned_at, alert_sent_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, '')",
                [(cid, terminal, lfd, status, fees, now, urgency, location, now) for cid, terminal, status, fees, lfd, urgency, location in seeds],
            )
        return len(seeds)

    async def upsert(
        self,
        container_id: str,
        terminal_id: str,
        result: ContainerStatusResponse,
    ) -> dict[str, Any]:
        polled_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watchlist_containers
                    (container_id, terminal_id, last_free_day, status, fees_due, last_polled_at, holds, urgency_level, notes, pinned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(container_id) DO UPDATE SET
                    terminal_id=excluded.terminal_id,
                    last_free_day=excluded.last_free_day,
                    status=excluded.status,
                    fees_due=excluded.fees_due,
                    last_polled_at=excluded.last_polled_at,
                    holds=excluded.holds, urgency_level=excluded.urgency_level, notes=excluded.notes
                """,
                (container_id.strip().upper(), terminal_id, result.last_free_day, result.status, result.fees_due, polled_at,
                 int(result.customs_hold), "CRITICAL" if result.fees_due > 0 else "SAFE", result.notes or "", polled_at),
            )
        return {
            "container_id": container_id.strip().upper(),
            "terminal_id": terminal_id,
            "last_free_day": result.last_free_day,
            "status": result.status,
            "fees_due": result.fees_due,
            "last_polled_at": polled_at,
            "holds": int(result.customs_hold),
            "urgency_level": "CRITICAL" if result.fees_due > 0 else "SAFE",
            "notes": result.notes or "",
            "pinned_at": polled_at,
        }

    async def list_all(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, container_id, terminal_id, last_free_day, status, fees_due, last_polled_at, holds, urgency_level, notes, pinned_at, alert_sent_at
                FROM watchlist_containers
                ORDER BY CASE WHEN last_free_day GLOB '????-??-??' THEN last_free_day ELSE '9999-12-31' END,
                         container_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    async def claim_alert(self, container_id: str) -> bool:
        """Atomically claim one alert slot for the current free-day cycle."""

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE watchlist_containers SET alert_sent_at = ? WHERE container_id = ? AND (alert_sent_at = '' OR alert_sent_at IS NULL)",
                (now, container_id.strip().upper()),
            )
            return cursor.rowcount == 1

    async def remove(self, container_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM watchlist_containers WHERE container_id = ?",
                (container_id.strip().upper(),),
            )
            return cursor.rowcount > 0
