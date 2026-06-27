"""SerpApi 的 Google Flights 資料來源。

價格最準、即時，且含完整中轉機場資訊（via 過濾可精準運作）。
免費額度小（約 100 次/月），用盡時拋 QuotaExceeded 以便自動退回備援來源。
文件：https://serpapi.com/google-flights-api
"""
from __future__ import annotations

import requests

from ..flight_offer import FlightError, FlightOffer, QuotaExceeded

_ENDPOINT = "https://serpapi.com/search.json"


class SerpApiClient:
    name = "serpapi"

    def __init__(self, api_key: str):
        self._key = api_key
        self._session = requests.Session()

    def search_offers(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str | None = None,
        adults: int = 1,
        currency: str = "TWD",
        max_results: int = 30,
    ) -> list[FlightOffer]:
        params = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": depart_date,
            "currency": currency.upper(),
            "adults": adults,
            "type": "1" if return_date else "2",  # 1=來回, 2=單程
            "api_key": self._key,
            "hl": "zh-tw",
        }
        if return_date:
            params["return_date"] = return_date

        resp = self._session.get(_ENDPOINT, params=params, timeout=60)
        if resp.status_code == 429:
            raise QuotaExceeded("SerpApi 免費額度/速率用盡（429）")
        data = resp.json() if resp.content else {}
        error = data.get("error")
        if error:
            # SerpApi 額度用盡時是 200 + error 訊息，要靠字串判斷
            if "run out" in error.lower() or "limit" in error.lower():
                raise QuotaExceeded(f"SerpApi 額度用盡：{error}")
            raise FlightError(f"SerpApi 查價失敗：{error}")
        if resp.status_code != 200:
            raise FlightError(f"SerpApi 查價失敗：{resp.status_code} {resp.text}")

        return self._parse(data, currency)

    @staticmethod
    def _parse(data: dict, currency: str) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        groups = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        for group in groups:
            try:
                price = float(group["price"])
            except (KeyError, TypeError, ValueError):
                continue
            legs = group.get("flights", [])
            segments = [
                {
                    "from": (leg.get("departure_airport") or {}).get("id"),
                    "to": (leg.get("arrival_airport") or {}).get("id"),
                    "departure": (leg.get("departure_airport") or {}).get("time"),
                }
                for leg in legs
            ]
            carrier = legs[0].get("airline", "") if legs else ""
            offers.append(
                FlightOffer(
                    price=price,
                    currency=currency.upper(),
                    carrier=carrier,
                    stops=max(0, len(legs) - 1),
                    segments=segments,
                    layovers_known=True,
                    booking_link=data.get("search_metadata", {}).get(
                        "google_flights_url"
                    ),
                )
            )
        return offers
