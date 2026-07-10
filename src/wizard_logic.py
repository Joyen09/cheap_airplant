"""按鈕式建立監控（精靈）的純邏輯：不碰 Discord API，方便測試。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from statistics import median

from .flight_offer import FlightOffer
from .parser import _parse_one_date, _resolve_place


@dataclass
class Draft:
    """建立中的監控草稿。"""
    origin: str | None = None
    destination: str | None = None
    depart_date: str | None = None
    return_date: str | None = None
    threshold: float | None = None
    vias: list[str] = field(default_factory=list)
    time_filters: dict = field(default_factory=dict)

    @property
    def via_str(self) -> str | None:
        return ",".join(self.vias) if self.vias else None

    @property
    def time_filters_json(self) -> str | None:
        return json.dumps(self.time_filters) if self.time_filters else None


def resolve_place(text: str) -> str | None:
    """城市中文/英文名或 IATA → 代碼；認不得回 None。"""
    return _resolve_place((text or "").strip())


def parse_date_input(text: str, today: date | None = None) -> str | None:
    """'9/26'、'2026-09-26'、'9月26日' → ISO；認不得回 None。"""
    return _parse_one_date((text or "").strip(), today or date.today())


def parse_budget_input(text: str) -> float | None:
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def parse_vias_input(text: str) -> tuple[list[str], list[str]]:
    """'香港, ICN' → (['HKG','ICN'], [認不得的字])。"""
    codes: list[str] = []
    bad: list[str] = []
    for token in (text or "").replace("、", ",").split(","):
        token = token.strip()
        if not token:
            continue
        code = resolve_place(token)
        if code and code not in codes:
            codes.append(code)
        elif not code:
            bad.append(token)
    return codes, bad


# ── 時段預設（下拉選單用）───────────────────────────────────────────────────
# key → (顯示文字, 方向, HH:MM)；方向 None = 清除限制。
# 涵蓋較完整的整點時段（Discord 單一選單上限 25 個）。
_AFTER_HOURS = [5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20]
_BEFORE_HOURS = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 23]


def _build_time_presets() -> dict[str, tuple[str, str | None, str | None]]:
    presets: dict[str, tuple[str, str | None, str | None]] = {
        "any": ("不限時間", None, None),
    }
    for h in _AFTER_HOURS:
        presets[f"after{h:02d}"] = (f"{h:02d}:00 以後", "after", f"{h:02d}:00")
    for h in _BEFORE_HOURS:
        presets[f"before{h:02d}"] = (f"{h:02d}:00 以前", "before", f"{h:02d}:00")
    return presets


TIME_PRESETS: dict[str, tuple[str, str | None, str | None]] = _build_time_presets()


def apply_time_preset(draft: Draft, leg: str, preset_key: str) -> None:
    """leg: 'out' 或 'ret'。套用/清除該航段的時段限制。"""
    _, direction, hhmm = TIME_PRESETS[preset_key]
    set_time_filter(draft, leg, direction, hhmm)


def set_time_filter(draft: Draft, leg: str,
                    direction: str | None, hhmm: str | None) -> None:
    """直接設定某航段的時段限制。direction=None 表示清除。"""
    draft.time_filters.pop(f"{leg}_before", None)
    draft.time_filters.pop(f"{leg}_after", None)
    if direction and hhmm:
        draft.time_filters[f"{leg}_{direction}"] = hhmm


def parse_time_input(text: str) -> tuple[str, str] | None:
    """把使用者打的時間條件轉成 (方向, HH:MM)。

    接受：「09:00後」「9點後」「18:00 以前」「6前」「after 9」「before 18:30」。
    空字串／「不限」回 None（= 清除限制）。看不懂就拋 ValueError。
    """
    t = (text or "").strip()
    if not t or t in ("不限", "無", "无", "any", "-"):
        return None
    tl = t.lower()
    if "前" in t or "before" in tl:
        direction = "before"
    elif "後" in t or "后" in t or "after" in tl:
        direction = "after"
    else:
        raise ValueError(f"看不懂「{text}」：要寫 前 或 後（例：09:00後、18:00前）")
    m = re.search(r"(\d{1,2})(?::(\d{2}))?", t)
    if not m:
        raise ValueError(f"看不懂「{text}」的時間（例：09:00後、6點前）")
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"「{text}」的時間超出範圍（小時 0-23、分鐘 0-59）")
    return direction, f"{hour:02d}:{minute:02d}"


# ── 行情摘要與預算建議 ────────────────────────────────────────────────────────
def price_context(offers: list[FlightOffer]) -> dict | None:
    """整理目前行情：最低價（含航司/轉次）、中位數、樣本數。"""
    if not offers:
        return None
    cheapest = min(offers, key=lambda o: o.price)
    prices = [o.price for o in offers]
    return {
        "low": cheapest.price,
        "median": float(median(prices)),
        "count": len(prices),
        "carrier": cheapest.carrier,
        "stops": cheapest.stops,
        "currency": cheapest.currency,
    }


def suggest_budgets(low: float) -> list[tuple[str, float]]:
    """依目前最低價給三檔建議預算（四捨五入到百位）。"""
    out = []
    for pct in (5, 10, 15):
        value = round(low * (1 - pct / 100) / 100) * 100
        if value > 0:
            out.append((f"便宜{pct}%（{value:.0f}）", float(value)))
    return out


def summarize_draft(draft: Draft) -> list[str]:
    """草稿的人類可讀摘要（給確認卡片用）。"""
    trip = f"{draft.depart_date} ↔ {draft.return_date}" if draft.return_date \
        else f"{draft.depart_date}（單程）"
    lines = [f"✈️ {draft.origin} → {draft.destination}　{trip}"]
    if draft.vias:
        lines.append(f"🔁 轉機點：{'、'.join(draft.vias)}")
    tf = draft.time_filters
    tparts = []
    if tf.get("out_after"):
        tparts.append(f"去程 {tf['out_after']} 後")
    if tf.get("out_before"):
        tparts.append(f"去程 {tf['out_before']} 前")
    if tf.get("ret_after"):
        tparts.append(f"回程 {tf['ret_after']} 後")
    if tf.get("ret_before"):
        tparts.append(f"回程 {tf['ret_before']} 前")
    if tparts:
        lines.append("🕒 " + "、".join(tparts))
    lines.append(
        f"💰 預算：{draft.threshold:.0f}" if draft.threshold
        else "💰 預算：未設（僅創新低/好價時通知）"
    )
    return lines


def validate_core(origin_raw: str, dest_raw: str, depart_raw: str,
                  return_raw: str, budget_raw: str,
                  today: date | None = None) -> tuple[Draft | None, list[str]]:
    """驗證表單五欄。回傳 (Draft, 錯誤清單)；有錯誤時 Draft 為 None。"""
    errors: list[str] = []
    origin = resolve_place(origin_raw)
    dest = resolve_place(dest_raw)
    depart = parse_date_input(depart_raw, today)
    ret = parse_date_input(return_raw, today) if (return_raw or "").strip() else None
    budget = parse_budget_input(budget_raw)

    if not origin:
        errors.append(f"看不懂出發地「{origin_raw}」（可填 TPE 或 台北）")
    if not dest:
        errors.append(f"看不懂目的地「{dest_raw}」")
    if not depart:
        errors.append(f"看不懂去程日期「{depart_raw}」（可填 9/26 或 2026-09-26）")
    if (return_raw or "").strip() and not ret:
        errors.append(f"看不懂回程日期「{return_raw}」")
    if ret and depart and ret < depart:
        errors.append("回程日期比去程還早")
    if (budget_raw or "").strip() and budget is None:
        errors.append(f"看不懂預算「{budget_raw}」（填數字即可）")

    if errors:
        return None, errors
    return Draft(origin=origin, destination=dest, depart_date=depart,
                 return_date=ret, threshold=budget), []
