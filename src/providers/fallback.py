"""把「主要來源」與「備援來源」串起來：主要來源額度用盡時自動退回備援。

符合需求：平常走較準的來源，超量（QuotaExceeded）就改走免費的 Travelpayouts。
"""
from __future__ import annotations

import logging

from ..flight_offer import FlightError, FlightOffer, QuotaExceeded

logger = logging.getLogger(__name__)


class FallbackProvider:
    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}->{fallback.name}"
        self.last_used = self.name  # 最近一次實際回應的來源

    def search_offers(self, **kwargs) -> list[FlightOffer]:
        try:
            offers = self.primary.search_offers(**kwargs)
            self.last_used = self.primary.name
            return offers
        except FlightError as exc:
            # 額度用盡、或查無結果、或任何暫時性錯誤 → 一律改用免費備援再試一次
            kind = "額度用盡" if isinstance(exc, QuotaExceeded) else "查詢失敗"
            logger.warning(
                "主要來源 %s %s（%s），改用備援 %s",
                self.primary.name, kind, exc, self.fallback.name,
            )
            self.last_used = self.fallback.name
            return self.fallback.search_offers(**kwargs)
