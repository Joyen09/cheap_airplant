"""SQLite 儲存：保存每個使用者建立的機票監控。"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Watch:
    id: int
    chat_id: int
    origin: str
    destination: str
    via: str | None
    depart_date: str
    return_date: str | None
    threshold: float | None
    currency: str
    lowest_seen: float | None
    active: int
    created_at: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER NOT NULL,
    origin       TEXT    NOT NULL,
    destination  TEXT    NOT NULL,
    via          TEXT,
    depart_date  TEXT    NOT NULL,
    return_date  TEXT,
    threshold    REAL,
    currency     TEXT    NOT NULL DEFAULT 'TWD',
    lowest_seen  REAL,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL
);
"""


class Storage:
    def __init__(self, db_path: str):
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_watch(row: sqlite3.Row) -> Watch:
        return Watch(**{k: row[k] for k in row.keys()})

    def add_watch(
        self,
        chat_id: int,
        origin: str,
        destination: str,
        via: str | None,
        depart_date: str,
        return_date: str | None,
        threshold: float | None,
        currency: str,
    ) -> Watch:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """INSERT INTO watches
               (chat_id, origin, destination, via, depart_date, return_date,
                threshold, currency, lowest_seen, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?)""",
            (chat_id, origin, destination, via, depart_date, return_date,
             threshold, currency, now),
        )
        self._conn.commit()
        return self.get_watch(cur.lastrowid)  # type: ignore[arg-type]

    def get_watch(self, watch_id: int) -> Watch | None:
        row = self._conn.execute(
            "SELECT * FROM watches WHERE id = ?", (watch_id,)
        ).fetchone()
        return self._row_to_watch(row) if row else None

    def list_watches(self, chat_id: int, active_only: bool = True) -> list[Watch]:
        sql = "SELECT * FROM watches WHERE chat_id = ?"
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY id"
        rows = self._conn.execute(sql, (chat_id,)).fetchall()
        return [self._row_to_watch(r) for r in rows]

    def all_active_watches(self) -> list[Watch]:
        rows = self._conn.execute(
            "SELECT * FROM watches WHERE active = 1 ORDER BY id"
        ).fetchall()
        return [self._row_to_watch(r) for r in rows]

    def update_lowest_seen(self, watch_id: int, price: float) -> None:
        self._conn.execute(
            "UPDATE watches SET lowest_seen = ? WHERE id = ?", (price, watch_id)
        )
        self._conn.commit()

    def deactivate(self, watch_id: int, chat_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE watches SET active = 0 WHERE id = ? AND chat_id = ?",
            (watch_id, chat_id),
        )
        self._conn.commit()
        return cur.rowcount > 0
