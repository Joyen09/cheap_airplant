from src.flight_offer import FlightOffer
from src.monitor import evaluate
from src.storage import Watch


def make_watch(threshold=None, lowest_seen=None, via=None,
               price_count=0, price_sum=0.0, last_alert_price=None,
               time_filters=None) -> Watch:
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
        price_count=price_count,
        price_sum=price_sum,
        last_alert_price=last_alert_price,
        time_filters=time_filters,
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


def test_above_threshold_no_notify():
    r = evaluate(make_watch(threshold=8000), [offer(9000)])
    assert not r.should_notify


def test_any_new_low_notifies():
    # 之前最低 10000，現在 9900（只跌 1% 也算新低）→ 通知
    r = evaluate(make_watch(lowest_seen=10000), [offer(9900)])
    assert r.should_notify
    assert "創新低" in r.reason


def test_not_a_new_low_stays_silent():
    # 沒有預算、現價不低於看過的最低 → 不吵
    r = evaluate(make_watch(lowest_seen=9000), [offer(9000)])
    assert not r.should_notify


def test_no_repeat_alert_until_cheaper():
    # 已在 9000 通知過，現價同樣 9000（仍低於預算）→ 不重複通知
    w = make_watch(threshold=10000, lowest_seen=9000, last_alert_price=9000)
    assert not evaluate(w, [offer(9000)]).should_notify
    # 再更便宜 → 重新通知
    assert evaluate(w, [offer(8500)]).should_notify


def test_good_deal_vs_baseline():
    # 常態價 = 12000（120000/10），現價 9000 → 低於 15% 門檻 → 好價
    w = make_watch(price_count=10, price_sum=120000.0)
    r = evaluate(w, [offer(9000)], good_deal_ratio=0.15)
    assert r.should_notify
    assert r.is_good_deal
    assert r.baseline == 12000


def test_good_deal_needs_enough_samples():
    # 樣本不足（< baseline_min_samples）→ 即使便宜也先不判好價
    w = make_watch(price_count=3, price_sum=36000.0)
    r = evaluate(w, [offer(9000)], good_deal_ratio=0.15, baseline_min_samples=10)
    assert not r.is_good_deal


def test_via_filter_matches_and_notifies():
    w = make_watch(threshold=13000, via="HKG")
    r = evaluate(w, [offer(9000), offer(12000, via_to="HKG")])
    assert r.cheapest.price == 12000
    assert r.should_notify


def test_multiple_vias_require_all():
    # 需要同時經 HKG 與 ICN；只經 HKG 的不算
    w = make_watch(threshold=99999, via="HKG,ICN")
    only_hkg = FlightOffer(price=8000, currency="TWD", carrier="X", stops=1,
                           segments=[{"from": "TPE", "to": "HKG"},
                                     {"from": "HKG", "to": "NRT"}])
    both = FlightOffer(price=12000, currency="TWD", carrier="Y", stops=2,
                       segments=[{"from": "TPE", "to": "HKG"},
                                 {"from": "HKG", "to": "ICN"},
                                 {"from": "ICN", "to": "NRT"}])
    r = evaluate(w, [only_hkg, both])
    assert r.cheapest.price == 12000   # 只有經過兩個點的才符合


def test_time_filter_outbound_before():
    w = make_watch(threshold=99999, time_filters='{"out_before":"12:00"}')
    early = FlightOffer(price=9000, currency="TWD", carrier="A", stops=0,
                        segments=[{"from": "TPE", "to": "NRT",
                                   "departure": "2026-07-01 08:30"}])
    late = FlightOffer(price=7000, currency="TWD", carrier="B", stops=0,
                       segments=[{"from": "TPE", "to": "NRT",
                                  "departure": "2026-07-01 15:00"}])
    r = evaluate(w, [early, late])
    assert r.cheapest.price == 9000    # 便宜的 15:00 被時間條件排除


def test_time_filter_skips_when_unknown():
    # 回程時刻未知（return_departure=None）→ 回程條件不排除
    w = make_watch(threshold=99999, time_filters='{"ret_before":"12:00"}')
    o = FlightOffer(price=9000, currency="TWD", carrier="A", stops=0,
                    segments=[{"from": "TPE", "to": "NRT",
                               "departure": "2026-07-01 08:30"}])
    r = evaluate(w, [o])
    assert r.cheapest.price == 9000


def test_baseline_prefers_rolling_over_lifetime():
    # 終身平均 100000（被早期高價灌爆），滾動視窗平均 12000 → 應以滾動視窗為準
    w = make_watch(price_count=10, price_sum=1_000_000.0)
    w.baseline = 12000.0
    r = evaluate(w, [offer(10000)], good_deal_ratio=0.15, baseline_min_samples=10)
    assert r.baseline == 12000.0
    assert r.is_good_deal  # 10000 <= 12000 * 0.85


def test_baseline_falls_back_to_lifetime_for_old_state():
    # 舊狀態檔沒有 baseline 欄位 → 退回累積平均，行為與過去相同
    w = make_watch(price_count=10, price_sum=120000.0)
    assert w.baseline is None
    r = evaluate(w, [offer(10000)], good_deal_ratio=0.15, baseline_min_samples=10)
    assert r.baseline == 12000.0
    assert r.is_good_deal
