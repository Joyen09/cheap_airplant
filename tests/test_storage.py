"""SQLite Storage 的常態價（滾動視窗）測試。"""
from datetime import datetime, timedelta, timezone

from src.storage import BASELINE_WINDOW_DAYS, Storage


def test_sqlite_baseline_uses_rolling_window_only(tmp_path):
    store = Storage(str(tmp_path / "t.db"))
    w = store.add_watch(1, "TPE", "NRT", None, "2026-07-01", None, None, "TWD")
    # 視窗外的舊高價：不應影響常態價
    old_ts = (
        datetime.now(timezone.utc) - timedelta(days=BASELINE_WINDOW_DAYS + 5)
    ).isoformat()
    store._conn.execute(
        "INSERT INTO price_history (watch_id, ts, price) VALUES (?, ?, ?)",
        (w.id, old_ts, 99999.0),
    )
    store.record_observation(w.id, 10000.0)
    store.record_observation(w.id, 12000.0)
    got = store.get_watch(w.id)
    assert got.baseline == 11000.0
    assert got.lowest_seen == 10000.0
    store.close()


def test_sqlite_migration_adds_baseline_column(tmp_path):
    # 開兩次同一個 DB：第二次的 ALTER TABLE 因欄位已存在會被忽略，不應報錯
    path = str(tmp_path / "m.db")
    Storage(path).close()
    store = Storage(path)
    w = store.add_watch(1, "TPE", "KIX", None, "2026-08-01", None, None, "TWD")
    assert w.baseline is None
    store.close()
