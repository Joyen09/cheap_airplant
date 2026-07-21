"""SQLite 儲存：保存每個使用者建立的機票監控。"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# 「常態價」的滾動視窗天數：只用最近這段期間的觀測算平均。
# 機票越接近出發日通常越貴，終身累積平均會被早期低價拉低、造成「好價」誤報，
# 所以基準只看近期。
BASELINE_WINDOW_DAYS = 14


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
    # 累積統計：樣本數門檻用；舊狀態檔沒有 baseline 時也用它退回累積平均
    price_count: int = 0
    price_sum: float = 0.0
    # 「常態價」基準：最近 BASELINE_WINDOW_DAYS 天觀測的平均（每次觀測時更新）
    baseline: float | None = None
    # 上次「主動通知」當下的價格；只有比這更便宜才會再通知，避免重複轟炸
    last_alert_price: float | None = None
    # 去程/回程時間限制的 JSON，例如 {"out_before":"18:00","ret_before":"12:00"}
    time_filters: str | None = None
    # 「這位使用者」的第幾個監控（顯示與指令都用這個；id 只當內部主鍵）
    user_seq: int = 0

    @property
    def display_no(self) -> int:
        return self.user_seq or self.id


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
    created_at   TEXT    NOT NULL,
    price_count  INTEGER NOT NULL DEFAULT 0,
    price_sum    REAL    NOT NULL DEFAULT 0,
    baseline     REAL,
    last_alert_price REAL,
    time_filters TEXT,
    user_seq     INTEGER
);
CREATE TABLE IF NOT EXISTS price_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id  INTEGER NOT NULL,
    ts        TEXT    NOT NULL,
    price     REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_watch ON price_history (watch_id, id);
"""

# 舊資料庫補欄位用（欄位已存在時 sqlite 會丟錯，忽略即可）
_MIGRATIONS = [
    "ALTER TABLE watches ADD COLUMN price_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE watches ADD COLUMN price_sum REAL NOT NULL DEFAULT 0",
    "ALTER TABLE watches ADD COLUMN baseline REAL",
    "ALTER TABLE watches ADD COLUMN last_alert_price REAL",
    "ALTER TABLE watches ADD COLUMN time_filters TEXT",
    "ALTER TABLE watches ADD COLUMN user_seq INTEGER",
]


class Storage:
    def __init__(self, db_path: str):
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        for sql in _MIGRATIONS:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # 欄位已存在
        self._backfill_user_seq()
        self._conn.commit()

    def _backfill_user_seq(self) -> None:
        """舊資料補上每人獨立的編號（依建立順序 1..n）。"""
        rows = self._conn.execute(
            "SELECT id, chat_id FROM watches WHERE user_seq IS NULL ORDER BY id"
        ).fetchall()
        counters: dict[int, int] = {}
        for row in rows:
            chat = row["chat_id"]
            if chat not in counters:
                cur = self._conn.execute(
                    "SELECT COALESCE(MAX(user_seq), 0) FROM watches WHERE chat_id = ?",
                    (chat,),
                ).fetchone()
                counters[chat] = cur[0]
            counters[chat] += 1
            self._conn.execute(
                "UPDATE watches SET user_seq = ? WHERE id = ?",
                (counters[chat], row["id"]),
            )

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
        time_filters: str | None = None,
    ) -> Watch:
        now = datetime.now(timezone.utc).isoformat()
        # 每人自己的編號：含已刪除的取最大值+1，編號不重複使用
        seq = self._conn.execute(
            "SELECT COALESCE(MAX(user_seq), 0) + 1 FROM watches WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()[0]
        cur = self._conn.execute(
            """INSERT INTO watches
               (chat_id, origin, destination, via, depart_date, return_date,
                threshold, currency, lowest_seen, active, created_at, time_filters,
                user_seq)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?, ?, ?)""",
            (chat_id, origin, destination, via, depart_date, return_date,
             threshold, currency, now, time_filters, seq),
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

    def record_observation(self, watch_id: int, price: float) -> None:
        """記錄一次查到的價格：更新歷史最低、常態價（滾動視窗平均），並寫入歷史點。"""
        now = datetime.now(timezone.utc)
        self._conn.execute(
            "INSERT INTO price_history (watch_id, ts, price) VALUES (?, ?, ?)",
            (watch_id, now.isoformat(), price),
        )
        # ts 一律是同格式的 UTC isoformat 字串，字典序即時間序，可直接比較
        cutoff = (now - timedelta(days=BASELINE_WINDOW_DAYS)).isoformat()
        baseline = self._conn.execute(
            "SELECT AVG(price) FROM price_history WHERE watch_id = ? AND ts >= ?",
            (watch_id, cutoff),
        ).fetchone()[0]
        self._conn.execute(
            """UPDATE watches SET
                 lowest_seen = CASE
                     WHEN lowest_seen IS NULL OR ? < lowest_seen THEN ?
                     ELSE lowest_seen END,
                 price_count = price_count + 1,
                 price_sum   = price_sum + ?,
                 baseline    = ?
               WHERE id = ?""",
            (price, price, price, baseline, watch_id),
        )
        self._conn.commit()

    def get_history(self, watch_id: int, limit: int = 500) -> list[tuple[str, float]]:
        """回傳最近 limit 筆 (時間, 價格)，依時間由舊到新。"""
        rows = self._conn.execute(
            "SELECT ts, price FROM price_history WHERE watch_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (watch_id, limit),
        ).fetchall()
        return [(r["ts"], r["price"]) for r in reversed(rows)]

    def mark_alerted(self, watch_id: int, price: float) -> None:
        """記下這次通知的價格，之後只有更便宜才會再通知。"""
        self._conn.execute(
            "UPDATE watches SET last_alert_price = ? WHERE id = ?", (price, watch_id)
        )
        self._conn.commit()

    def deactivate(self, watch_id: int, chat_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE watches SET active = 0 WHERE id = ? AND chat_id = ?",
            (watch_id, chat_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def find_by_seq(self, chat_id: int, seq: int) -> Watch | None:
        """用使用者自己的編號找（僅限使用中的監控）。"""
        row = self._conn.execute(
            "SELECT * FROM watches WHERE chat_id = ? AND user_seq = ? AND active = 1",
            (chat_id, seq),
        ).fetchone()
        return self._row_to_watch(row) if row else None

    def deactivate_seq(self, chat_id: int, seq: int) -> bool:
        w = self.find_by_seq(chat_id, seq)
        return self.deactivate(w.id, chat_id) if w else False
