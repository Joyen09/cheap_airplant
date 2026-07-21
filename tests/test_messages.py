"""通知訊息的分潤連結測試。"""
from src.messages import _booking_section
from src.storage import Watch


def make_watch(return_date=None) -> Watch:
    return Watch(
        id=1, chat_id=99, origin="TPE", destination="NRT", via=None,
        depart_date="2026-10-01", return_date=return_date, threshold=None,
        currency="TWD", lowest_seen=None, active=1,
        created_at="2026-06-27T00:00:00+00:00",
    )


def test_affiliate_link_present_with_marker(monkeypatch):
    monkeypatch.setenv("TRAVELPAYOUTS_MARKER", "abc123")
    monkeypatch.setenv("ADULTS", "1")
    text = _booking_section(make_watch(return_date="2026-10-10"), None)
    # 來回：TPE + 0110(去程 日日月月) + NRT + 1010(回程) + 1(人數)
    assert "aviasales.com/search/TPE0110NRT10101" in text
    assert "marker=abc123" in text
    assert "分潤" in text  # 對使用者誠實揭露


def test_affiliate_link_one_way(monkeypatch):
    monkeypatch.setenv("TRAVELPAYOUTS_MARKER", "abc123")
    monkeypatch.setenv("ADULTS", "1")
    text = _booking_section(make_watch(), None)
    assert "aviasales.com/search/TPE0110NRT1" in text


def test_no_affiliate_link_without_marker(monkeypatch):
    monkeypatch.delenv("TRAVELPAYOUTS_MARKER", raising=False)
    text = _booking_section(make_watch(), None)
    assert "aviasales" not in text.lower()
