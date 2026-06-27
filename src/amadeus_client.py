"""Amadeus Self-Service API 用戶端：OAuth2 取 token + 查機票報價。"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

_HOSTS = {
    "test": "https://test.api.amadeus.com",
    "production": "https://api.amadeus.com",
}


@dataclass
class FlightOffer:
    price: float
    currency: str
    carrier: str
    stops: int
    segments: list[dict]  # 每段：{"from": IATA, "to": IATA, "departure": iso}

    def goes_via(self, via: str) -> bool:
        """這個報價的航程中是否經過指定轉乘機場。"""
        via = via.upper()
        for seg in self.segments:
            if seg.get("from") == via or seg.get("to") == via:
                return True
        return False


class AmadeusError(RuntimeError):
    pass


class AmadeusClient:
    def __init__(self, client_id: str, client_secret: str, env: str = "test"):
        self._client_id = client_id
        self._client_secret = client_secret
        self._host = _HOSTS.get(env, _HOSTS["test"])
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._session = requests.Session()

    # ── 驗證 ──────────────────────────────────────────────────────────────
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = self._session.post(
            f"{self._host}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise AmadeusError(f"取得 Amadeus token 失敗：{resp.status_code} {resp.text}")
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 1799)
        return self._token

    # ── 查價 ──────────────────────────────────────────────────────────────
    def search_offers(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str | None = None,
        adults: int = 1,
        currency: str = "TWD",
        max_results: int = 50,
    ) -> list[FlightOffer]:
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": depart_date,
            "adults": adults,
            "currencyCode": currency,
            "max": max_results,
        }
        if return_date:
            params["returnDate"] = return_date

        resp = self._session.get(
            f"{self._host}/v2/shopping/flight-offers",
            params=params,
            headers={"Authorization": f"Bearer {self._get_token()}"},
            timeout=60,
        )
        if resp.status_code != 200:
            raise AmadeusError(f"查機票失敗：{resp.status_code} {resp.text}")
        return self._parse_offers(resp.json())

    @staticmethod
    def _parse_offers(payload: dict) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        carriers = (payload.get("dictionaries") or {}).get("carriers", {})
        for raw in payload.get("data", []):
            price_info = raw.get("price", {})
            try:
                price = float(price_info.get("grandTotal") or price_info.get("total"))
            except (TypeError, ValueError):
                continue
            currency = price_info.get("currency", "")

            segments: list[dict] = []
            carrier_code = ""
            for itinerary in raw.get("itineraries", []):
                segs = itinerary.get("segments", [])
                for seg in segs:
                    if not carrier_code:
                        carrier_code = seg.get("carrierCode", "")
                    segments.append(
                        {
                            "from": seg.get("departure", {}).get("iataCode"),
                            "to": seg.get("arrival", {}).get("iataCode"),
                            "departure": seg.get("departure", {}).get("at"),
                        }
                    )
            # 轉機次數 = 第一段航程的 segment 數 - 1（去程）
            first_itin = (raw.get("itineraries") or [{}])[0]
            stops = max(0, len(first_itin.get("segments", [])) - 1)

            offers.append(
                FlightOffer(
                    price=price,
                    currency=currency,
                    carrier=carriers.get(carrier_code, carrier_code),
                    stops=stops,
                    segments=segments,
                )
            )
        return offers
