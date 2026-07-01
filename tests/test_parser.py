from datetime import date

from src.parser import parse_message

TODAY = date(2026, 6, 27)


def test_basic_round_trip_with_budget():
    p = parse_message("從 TPE 到 NRT 7/1 出發 7/10 回程 低於 12000", TODAY)
    assert p.ok
    assert p.origin == "TPE"
    assert p.destination == "NRT"
    assert p.via is None
    assert p.depart_date == "2026-07-01"
    assert p.return_date == "2026-07-10"
    assert p.threshold == 12000


def test_chinese_city_names_and_via():
    p = parse_message("台北 到 大阪 經 香港 2026-07-01 ~ 2026-07-10", TODAY)
    assert p.ok
    assert p.origin == "TPE"
    assert p.destination == "OSA"
    assert p.via == "HKG"
    assert p.depart_date == "2026-07-01"
    assert p.return_date == "2026-07-10"


def test_via_not_mistaken_for_destination():
    # 「經 東京」不應該被當成目的地
    p = parse_message("TPE 到 KIX 經 東京 8/15", TODAY)
    assert p.destination == "KIX"
    assert p.via == "TYO"


def test_one_way_ignores_second_date():
    p = parse_message("TPE -> KIX 8/15 單程", TODAY)
    assert p.ok
    assert p.return_date is None
    assert p.depart_date == "2026-08-15"


def test_past_date_rolls_to_next_year():
    # 1/5 已經過了（今天 6/27），應補成明年
    p = parse_message("TPE 到 HKG 1/5", TODAY)
    assert p.depart_date == "2027-01-05"


def test_missing_info_reports_error():
    p = parse_message("我想去日本玩", TODAY)
    assert not p.ok
    assert p.error is not None


def test_arrow_route_with_threshold_symbol():
    p = parse_message("TPE→FUK 9/9 <8000", TODAY)
    assert p.origin == "TPE"
    assert p.destination == "FUK"
    assert p.threshold == 8000


def test_multiple_vias():
    p = parse_message("台北 到 NRT 中轉 YXY 轉 KIX 9/26 出發 10/4 回程 低於 25000", TODAY)
    assert p.ok
    assert p.origin == "TPE"
    assert p.destination == "NRT"
    assert p.via == "YXY,KIX"           # 兩個轉乘點
    assert p.depart_date == "2026-09-26"
    assert p.return_date == "2026-10-04"
    assert p.threshold == 25000


def test_time_filters():
    import json
    p = parse_message("TPE 到 NRT 9/26 去程 18:00 前 回程 6點 後", TODAY)
    assert p.ok
    tf = json.loads(p.time_filters)
    assert tf == {"out_before": "18:00", "ret_after": "06:00"}


def test_no_time_filters():
    p = parse_message("TPE 到 NRT 9/26", TODAY)
    assert p.time_filters is None
