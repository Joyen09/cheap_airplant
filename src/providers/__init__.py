"""依設定組出要用的機票資料來源。

順序（前面的失敗自動退到後面）：
  1. Google Flights（fast-flights，免費、即時、免 API key）— 永遠是主力
  2. SerpApi（設定 SERPAPI_KEY 才加入）— 額度內的備援
  3. Travelpayouts（設定 TRAVELPAYOUTS_TOKEN 才加入）— 免費快取備援
"""
from __future__ import annotations

from .fallback import FallbackProvider
from .google_flights import GoogleFlightsClient
from .serpapi import SerpApiClient
from .travelpayouts import TravelpayoutsClient


def build_provider(config):
    chain = [GoogleFlightsClient()]
    if getattr(config, "serpapi_key", ""):
        chain.append(SerpApiClient(config.serpapi_key))
    if getattr(config, "travelpayouts_token", ""):
        chain.append(TravelpayoutsClient(config.travelpayouts_token))

    provider = chain[-1]
    for p in reversed(chain[:-1]):
        provider = FallbackProvider(primary=p, fallback=provider)
    return provider


__all__ = [
    "build_provider",
    "FallbackProvider",
    "GoogleFlightsClient",
    "SerpApiClient",
    "TravelpayoutsClient",
]
