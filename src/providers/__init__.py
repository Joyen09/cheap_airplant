"""依設定組出要用的機票資料來源。

規則（符合「兩種都接，超量走免費的」）：
  * 同時有 SerpApi 與 Travelpayouts → 主要用 SerpApi（準），額度用盡自動退回 Travelpayouts。
  * 只有其中一個 → 就用那一個。
  * 都沒有 → 報錯，請去設定 token。
"""
from __future__ import annotations

from .fallback import FallbackProvider
from .serpapi import SerpApiClient
from .travelpayouts import TravelpayoutsClient


def build_provider(config):
    tp = (
        TravelpayoutsClient(config.travelpayouts_token)
        if config.travelpayouts_token
        else None
    )
    serp = SerpApiClient(config.serpapi_key) if config.serpapi_key else None

    if serp and tp:
        # 平常走 SerpApi（即時、可精準 via），超量退回免費的 Travelpayouts
        return FallbackProvider(primary=serp, fallback=tp)
    if serp:
        return serp
    if tp:
        return tp
    raise RuntimeError(
        "沒有設定任何機票資料來源。請至少設定 TRAVELPAYOUTS_TOKEN "
        "或 SERPAPI_KEY 其中一個（見 .env.example）。"
    )


__all__ = ["build_provider", "FallbackProvider", "SerpApiClient", "TravelpayoutsClient"]
