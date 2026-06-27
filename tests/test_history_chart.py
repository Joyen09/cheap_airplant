import pytest

from src.json_storage import JsonStorage
from src.storage import Storage


def test_json_history_roundtrip_and_cap(tmp_path):
    store = JsonStorage(str(tmp_path / "s.json"))
    w = store.add_watch(7, "TPE", "NRT", None, "2026-07-01", None, 12000, "TWD")
    for p in range(1100):  # 超過 1000 上限
        store.record_observation(w.id, 10000 + p)
    store.save()

    reloaded = JsonStorage(str(tmp_path / "s.json"))
    hist = reloaded.get_history(w.id, limit=5000)
    assert len(hist) == 1000           # 被裁到上限
    assert hist[-1][1] == 10000 + 1099  # 保留最新的
    assert reloaded.list_watches(7)[0].price_count == 1100


def test_sqlite_history(tmp_path):
    s = Storage(str(tmp_path / "w.db"))
    w = s.add_watch(7, "TPE", "NRT", None, "2026-07-01", None, 12000, "TWD")
    s.record_observation(w.id, 12000)
    s.record_observation(w.id, 11000)
    hist = s.get_history(w.id)
    assert [p for _, p in hist] == [12000, 11000]   # 由舊到新


def test_chart_renders_png():
    plt = pytest.importorskip("matplotlib")  # 沒裝就跳過
    from src.chart import render_price_chart
    points = [
        ("2026-06-27T00:00:00+00:00", 12000),
        ("2026-06-27T01:00:00+00:00", 11000),
        ("2026-06-27T02:00:00+00:00", 9500),
    ]
    png = render_price_chart("TPE-NRT 2026-07-01", points,
                             threshold=12000, baseline=10800)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number
    assert len(png) > 1000
