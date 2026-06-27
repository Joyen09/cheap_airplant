from src.flight_offer import FlightOffer
from src.monitor import evaluate
from src.storage import Watch


def make_watch(threshold=None, lowest_seen=None, via=None) -> Watch:
    return Watch(
        id=1,
        chat_id=99,
        origin="TPE",
        destination="NRT",
        via=via,
        depart_date="2026-07-01",
        return_date=None,
        threshold=threshold,
        currency="TWD",
        lowest_seen=lowest_seen,
        active=1,
        created_at="2026-06-27T00:00:00+00:00",
    )


def offer(price, via_from=None, via_to=None) -> FlightOffer:
    segs = [{"from": "TPE", "to": "NRT", "departure": "2026-07-01T08:00"}]
    if via_from or via_to:
        segs = [
            {"from": "TPE", "to": via_to or via_from, "departure": "2026-07-01T08:00"},
            {"from": via_to or via_from, "to": "NRT", "departure": "2026-07-01T12:00"},
        ]
    return FlightOffer(price=price, currency="TWD", carrier="XX",
                       stops=len(segs) - 1, segments=segs)


def test_no_offers_no_notify():
    r = evaluate(make_watch(threshold=10000), [])
    assert not r.should_notify
    assert r.cheapest is None


def test_below_threshold_notifies():
    r = evaluate(make_watch(threshold=10000), [offer(9000), offer(15000)])
    assert r.should_notify
    assert r.cheapest.price == 9000


def test_above_threshold_no_notify_but_records_baseline():
    r = evaluate(make_watch(threshold=8000), [offer(9000)])
    assert not r.should_notify
    assert r.new_lowest == 9000  # 第一次查記錄基準


def test_new_low_notifies():
    # 之前最低 10000，現在 9000（跌超過 5%）→ 通知
    r = evaluate(make_watch(lowest_seen=10000), [offer(9000)])
    assert r.should_notify
    assert r.new_lowest == 9000


def test_tiny_drop_updates_baseline_without_notify():
    # 之前 10000，現在 9900（只跌 1%）→ 更新但不打擾
    r = evaluate(make_watch(lowest_seen=10000), [offer(9900)])
    assert not r.should_notify
    assert r.new_lowest == 9900


def test_via_filter_excludes_non_matching():
    w = make_watch(threshold=10000, via="HKG")
    # 9000 不經 HKG、12000 經 HKG → 只有 12000 符合，但超過預算
    r = evaluate(w, [offer(9000), offer(12000, via_to="HKG")])
    assert r.cheapest.price == 12000
    assert not r.should_notify


def test_via_filter_matches_and_notifies():
    w = make_watch(threshold=13000, via="HKG")
    r = evaluate(w, [offer(9000), offer(12000, via_to="HKG")])
    assert r.cheapest.price == 12000
    assert r.should_notify
