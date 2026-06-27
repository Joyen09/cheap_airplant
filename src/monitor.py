"""判價邏輯：查一個監控的目前最低價，並決定是否該通知。"""
from __future__ import annotations

from dataclasses import dataclass

from .amadeus_client import AmadeusClient, FlightOffer
from .storage import Watch


@dataclass
class CheckResult:
    watch: Watch
    cheapest: FlightOffer | None
    should_notify: bool
    reason: str          # 為什麼通知（給人看的）
    new_lowest: float | None  # 若刷新歷史最低，這裡放新值


def _cheapest_matching(
    offers: list[FlightOffer], via: str | None
) -> FlightOffer | None:
    candidates = offers
    if via:
        candidates = [o for o in offers if o.goes_via(via)]
    if not candidates:
        return None
    return min(candidates, key=lambda o: o.price)


def evaluate(
    watch: Watch,
    offers: list[FlightOffer],
    new_low_ratio: float = 0.05,
) -> CheckResult:
    """純函式：給定報價清單，判斷是否該通知。不碰網路、不碰 DB。"""
    cheapest = _cheapest_matching(offers, watch.via)
    if cheapest is None:
        return CheckResult(watch, None, False, "查無符合條件的航班", None)

    price = cheapest.price
    notify = False
    reasons: list[str] = []
    new_lowest: float | None = None

    # 條件一：低於使用者設定的預算
    if watch.threshold is not None and price <= watch.threshold:
        notify = True
        reasons.append(f"低於你的預算 {watch.threshold:.0f}")

    # 條件二：刷新歷史最低（且明顯更便宜）
    if watch.lowest_seen is None:
        new_lowest = price  # 第一次查，記錄基準但不通知
    elif price < watch.lowest_seen * (1 - new_low_ratio):
        notify = True
        new_lowest = price
        drop = watch.lowest_seen - price
        reasons.append(
            f"創新低！比之前最低的 {watch.lowest_seen:.0f} 再便宜 {drop:.0f}"
        )
    elif price < watch.lowest_seen:
        new_lowest = price  # 小幅新低，更新基準但不打擾

    reason = "；".join(reasons) if reasons else "價格沒有明顯變化"
    return CheckResult(watch, cheapest, notify, reason, new_lowest)


def check_watch(
    client: AmadeusClient,
    watch: Watch,
    adults: int = 1,
    new_low_ratio: float = 0.05,
) -> CheckResult:
    """實際查 Amadeus，再交給 evaluate 判斷。"""
    offers = client.search_offers(
        origin=watch.origin,
        destination=watch.destination,
        depart_date=watch.depart_date,
        return_date=watch.return_date,
        adults=adults,
        currency=watch.currency,
    )
    return evaluate(watch, offers, new_low_ratio=new_low_ratio)
