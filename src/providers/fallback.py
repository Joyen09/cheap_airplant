"""把「主要來源」與「備援來源」串起來：主要來源額度用盡時自動退回備援。

符合需求：平常走較準的來源，超量（QuotaExceeded）就改走免費的 Travelpayouts。
"""
from __future__ import annotations

import logging

from ..flight_offer import FlightOffer, QuotaExceeded

logger = logging.getLogger(__name__)


class FallbackProvider:
    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}->{fallback.name}"

    def search_offers(self, **kwargs) -> list[FlightOffer]:
        try:
            return self.primary.search_offers(**kwargs)
        except QuotaExceeded as exc:
            logger.warning(
                "主要來源 %s 額度用盡（%s），改用備援 %s",
                self.primary.name, exc, self.fallback.name,
            )
            return self.fallback.search_offers(**kwargs)
