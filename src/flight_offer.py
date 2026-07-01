"""所有機票資料來源共用的型別與例外。

把 FlightOffer 抽到這裡，讓各家 provider（Travelpayouts / SerpApi / …）
與 monitor、messages 都依賴同一個型別，互不耦合。
"""
from __future__ import annotations

from dataclasses import dataclass, field


class FlightError(RuntimeError):
    """查價失敗的共同基底例外。"""


class QuotaExceeded(FlightError):
    """API 免費額度/速率用盡。觸發時可自動退回備援來源。"""


@dataclass
class FlightOffer:
    price: float
    currency: str
    carrier: str
    stops: int
    # 每段航程：{"from": IATA, "to": IATA, "departure": iso}
    segments: list[dict] = field(default_factory=list)
    # 這筆報價是否含完整的中轉機場資訊。快取型來源（Travelpayouts）只給轉乘
    # 次數、不給中轉機場，這時設 False，goes_via 會改用「無法否證」的寬鬆判斷。
    layovers_known: bool = True
    booking_link: str | None = None
    # 回程去程時刻（ISO 或含 HH:MM 的字串）；用於時間過濾。
    # 去程時刻取自 segments[0]；回程時刻部分來源才有（如 Travelpayouts 的 return_at）。
    return_departure: str | None = None

    def goes_via(self, via: str) -> bool:
        """這個報價是否經過指定的轉乘機場。"""
        via = via.upper()
        if self.layovers_known:
            return any(
                seg.get("from") == via or seg.get("to") == via
                for seg in self.segments
            )
        # 來源沒給中轉機場：無法證實也無法否證。至少要有轉乘才「可能」經過。
        return self.stops > 0
