"""判價邏輯：查一個監控的目前最低價，並決定是否該通知。

通知條件（任一成立就「值得通知」）：
  1. 低於使用者設定的預算
  2. 破歷史新低（比看過的最低更低）
  3. 好價：明顯低於這條航線的「常態價」（最近 BASELINE_WINDOW_DAYS 天觀測的平均）

為了不重複轟炸，只有當價格「比上次通知時更便宜」才會真的再次通知
（last_alert_price 機制）。常態價需要累積足夠樣本後才會啟用。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .flight_offer import FlightOffer
from .storage import Watch


@dataclass
class CheckResult:
    watch: Watch
    cheapest: FlightOffer | None
    should_notify: bool
    reason: str               # 為什麼通知（給人看的）
    baseline: float | None = None      # 目前估算的常態價
    is_good_deal: bool = False         # 是否明顯低於常態價


def baseline_of(watch: Watch) -> float | None:
    """這條航線的「常態價」基準。

    新資料用滾動視窗平均（storage 在每次觀測時更新 watch.baseline）；
    舊狀態檔還沒有 baseline 欄位時，退回終身累積平均。
    """
    if watch.baseline is not None:
        return watch.baseline
    if watch.price_count > 0:
        return watch.price_sum / watch.price_count
    return None


def _time_to_minutes(value: str | None) -> int | None:
    """從時刻字串取出當天的分鐘數（找第一個 HH:MM）。"""
    if not value:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", value)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _matches_vias(offer: FlightOffer, vias: list[str]) -> bool:
    if not vias:
        return True
    if offer.layovers_known:
        return all(offer.goes_via(v) for v in vias)
    # 來源沒有中轉機場資訊：至少轉乘次數要 >= 指定的轉乘點數
    return offer.stops >= len(vias)


def _passes_time(offer: FlightOffer, tf: dict) -> bool:
    if not tf:
        return True
    out_dep = _time_to_minutes(offer.segments[0]["departure"]) if offer.segments else None
    ret_dep = _time_to_minutes(offer.return_departure)

    def ok(val: int | None, before: str | None, after: str | None) -> bool:
        if val is None:      # 不知道時刻就不排除（盡力而為）
            return True
        if before and val > _time_to_minutes(before):
            return False
        if after and val < _time_to_minutes(after):
            return False
        return True

    return (
        ok(out_dep, tf.get("out_before"), tf.get("out_after"))
        and ok(ret_dep, tf.get("ret_before"), tf.get("ret_after"))
    )


def _cheapest_matching(offers: list[FlightOffer], watch: Watch) -> FlightOffer | None:
    vias = watch.via.split(",") if watch.via else []
    tf = json.loads(watch.time_filters) if watch.time_filters else {}
    candidates = [
        o for o in offers
        if _matches_vias(o, vias) and _passes_time(o, tf)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda o: o.price)


def evaluate(
    watch: Watch,
    offers: list[FlightOffer],
    good_deal_ratio: float = 0.15,
    baseline_min_samples: int = 10,
) -> CheckResult:
    """純函式：給定報價清單，判斷是否該通知。不碰網路、不碰 DB。

    用 watch 目前（更新前）的統計來判斷；實際的統計更新由呼叫端在事後
    呼叫 storage.record_observation / mark_alerted 完成。
    """
    cheapest = _cheapest_matching(offers, watch)
    if cheapest is None:
        return CheckResult(watch, None, False, "查無符合條件的航班")

    price = cheapest.price
    reasons: list[str] = []

    baseline = baseline_of(watch)
    has_baseline = baseline is not None and watch.price_count >= baseline_min_samples

    # 三種「值得通知」的情況
    below_budget = watch.threshold is not None and price <= watch.threshold
    is_new_low = watch.lowest_seen is not None and price < watch.lowest_seen
    is_good_deal = (
        has_baseline and price <= baseline * (1 - good_deal_ratio)
    )

    if below_budget:
        reasons.append(f"低於你的預算 {watch.threshold:.0f}")
    if is_new_low:
        drop = watch.lowest_seen - price
        reasons.append(f"創新低（比之前最低 {watch.lowest_seen:.0f} 再便宜 {drop:.0f}）")
    if is_good_deal:
        pct = (1 - price / baseline) * 100
        reasons.append(f"比常態價 {baseline:.0f} 便宜 {pct:.0f}%，是好價 🔥")

    notable = below_budget or is_new_low or is_good_deal
    # 只有比「上次通知的價格」更便宜，才真的再次通知（避免每 5 分鐘重複轟炸）
    cheaper_than_last = (
        watch.last_alert_price is None or price < watch.last_alert_price
    )
    should_notify = notable and cheaper_than_last

    reason = "；".join(reasons) if reasons else "價格沒有明顯變化"
    return CheckResult(
        watch, cheapest, should_notify, reason,
        baseline=baseline, is_good_deal=is_good_deal,
    )


def check_watch(
    client,
    watch: Watch,
    adults: int = 1,
    good_deal_ratio: float = 0.15,
    baseline_min_samples: int = 10,
) -> CheckResult:
    """實際向資料來源查價（任何有 search_offers 的 provider），再交給 evaluate 判斷。"""
    offers = client.search_offers(
        origin=watch.origin,
        destination=watch.destination,
        depart_date=watch.depart_date,
        return_date=watch.return_date,
        adults=adults,
        currency=watch.currency,
    )
    result = evaluate(
        watch, offers,
        good_deal_ratio=good_deal_ratio,
        baseline_min_samples=baseline_min_samples,
    )
    if result.cheapest is None:
        source = getattr(client, "last_used", getattr(client, "name", "?"))
        hint = "（快取價資料庫沒有這組日期的紀錄，之後查到會自動補上）" \
            if source == "travelpayouts" else ""
        result.reason = f"查無符合條件的航班｜來源：{source}{hint}"
    return result
