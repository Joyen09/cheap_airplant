from datetime import date

from src.flight_offer import FlightOffer
from src.wizard_logic import (
    Draft,
    apply_time_preset,
    parse_budget_input,
    parse_vias_input,
    price_context,
    suggest_budgets,
    summarize_draft,
    validate_core,
)

TODAY = date(2026, 7, 9)


def offer(price, stops=0, carrier="CI"):
    return FlightOffer(price=price, currency="TWD", carrier=carrier,
                       stops=stops, segments=[])


# ── 表單驗證 ─────────────────────────────────────────────────────────────────
def test_validate_ok_full():
    draft, errors = validate_core("台北", "NRT", "9/26", "10/4", "25000", TODAY)
    assert errors == []
    assert draft.origin == "TPE" and draft.destination == "NRT"
    assert draft.depart_date == "2026-09-26"
    assert draft.return_date == "2026-10-04"
    assert draft.threshold == 25000


def test_validate_one_way_no_budget():
    draft, errors = validate_core("HKG", "東京", "8/1", "", "", TODAY)
    assert errors == []
    assert draft.return_date is None and draft.threshold is None


def test_validate_collects_all_errors():
    draft, errors = validate_core("火星", "NRT", "昨天", "10/4", "很便宜", TODAY)
    assert draft is None
    assert len(errors) == 3  # 出發地、去程日期、預算


def test_validate_return_before_depart():
    draft, errors = validate_core("TPE", "NRT", "2026-10-04", "2026-09-26", "", TODAY)
    assert draft is None
    assert any("回程日期比去程還早" in e for e in errors)


# ── 轉機點 / 預算輸入 ────────────────────────────────────────────────────────
def test_parse_vias_mixed():
    codes, bad = parse_vias_input("香港, ICN、火星")
    assert codes == ["HKG", "ICN"]
    assert bad == ["火星"]


def test_parse_budget():
    assert parse_budget_input("25,000") == 25000
    assert parse_budget_input("") is None
    assert parse_budget_input("abc") is None
    assert parse_budget_input("-5") is None


# ── 時段預設 ─────────────────────────────────────────────────────────────────
def test_time_presets_apply_and_clear():
    d = Draft()
    apply_time_preset(d, "out", "after09")
    assert d.time_filters == {"out_after": "09:00"}
    apply_time_preset(d, "out", "before18")   # 換方向會清掉舊的
    assert d.time_filters == {"out_before": "18:00"}
    apply_time_preset(d, "ret", "after16")
    assert d.time_filters["ret_after"] == "16:00"
    apply_time_preset(d, "out", "any")        # 清除
    assert "out_before" not in d.time_filters
    assert d.time_filters == {"ret_after": "16:00"}


def test_set_time_filter_direct():
    from src.wizard_logic import set_time_filter
    d = Draft()
    set_time_filter(d, "out", "after", 6)
    assert d.time_filters == {"out_after": "06:00"}
    set_time_filter(d, "out", "before", 18)   # 換方向會清掉舊的
    assert d.time_filters == {"out_before": "18:00"}
    set_time_filter(d, "ret", "after", 27)    # 超過 24 要繞回（27→03）
    assert d.time_filters["ret_after"] == "03:00"
    set_time_filter(d, "out", None, 0)        # 清除
    assert d.time_filters == {"ret_after": "03:00"}


def test_all_presets_valid_and_within_discord_limit():
    from src.wizard_logic import TIME_PRESETS
    assert len(TIME_PRESETS) <= 25          # Discord 單一選單上限
    for key, (label, direction, hhmm) in TIME_PRESETS.items():
        assert direction in (None, "before", "after")
        if direction:
            assert hhmm and ":" in hhmm


# ── 行情與建議 ───────────────────────────────────────────────────────────────
def test_price_context_and_suggestions():
    ctx = price_context([offer(9000, carrier="HK Express"),
                         offer(12000), offer(15000)])
    assert ctx["low"] == 9000 and ctx["median"] == 12000 and ctx["count"] == 3
    assert ctx["carrier"] == "HK Express"
    tips = suggest_budgets(ctx["low"])
    assert [v for _, v in tips] == [8600, 8100, 7600]  # 四捨五入到百位


def test_price_context_empty():
    assert price_context([]) is None


def test_summary_lines():
    d = Draft(origin="TPE", destination="NRT", depart_date="2026-09-26",
              return_date="2026-10-04", threshold=25000,
              vias=["HKG"], time_filters={"out_after": "09:00"})
    text = "\n".join(summarize_draft(d))
    assert "TPE → NRT" in text and "HKG" in text
    assert "09:00 後" in text and "25000" in text
    assert d.via_str == "HKG"
    assert d.time_filters_json == '{"out_after": "09:00"}'
