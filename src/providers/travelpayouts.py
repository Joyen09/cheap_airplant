"""Travelpayouts（Aviasales）資料來源。

免費、靠訂票分潤獲利，不按 API 次數收費，因此高頻查詢也不會花錢。
用的是 v3 prices_for_dates 端點：回傳某航線在指定日期的「快取最低價」。
缺點：價格是別人搜過的快取結果（非即時），且只給轉乘次數、不給中轉機場。
文件：https://support.travelpayouts.com/hc/en-us/articles/203956163
"""
from __future__ import annotations

import requests

from ..flight_offer import FlightError, FlightOffer, QuotaExceeded

_ENDPOINT = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


class TravelpayoutsClient:
    name = "travelpayouts"

    def __init__(self, token: str):
        self._token = token
        self._session = requests.Session()

    def search_offers(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str | None = None,
        adults: int = 1,  # 此端點不分人數，保留簽名一致
        currency: str = "twd",
        max_results: int = 30,
    ) -> list[FlightOffer]:
        params = {
            "origin": origin,
            "destination": destination,
            "departure_at": depart_date,
            "currency": currency.lower(),
            "unique": "false",
            "sorting": "price",
            "direct": "false",
            "limit": max_results,
            "one_way": "true" if not return_date else "false",
            "token": self._token,
        }
        if return_date:
            params["return_at"] = return_date

        resp = self._session.get(_ENDPOINT, params=params, timeout=30)
        if resp.status_code in (401, 403):
            raise FlightError(f"Travelpayouts 授權失敗（token 有誤？）：{resp.text}")
        if resp.status_code == 429:
            raise QuotaExceeded(f"Travelpayouts 被限流：{resp.text}")
        if resp.status_code != 200:
            raise FlightError(f"Travelpayouts 查價失敗：{resp.status_code} {resp.text}")

        return self._parse(resp.json(), currency)

    @staticmethod
    def _parse(payload: dict, currency: str) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        for row in payload.get("data", []) or []:
            try:
                price = float(row["price"])
            except (KeyError, TypeError, ValueError):
                continue
            transfers = int(row.get("transfers", 0) or 0)
            offers.append(
                FlightOffer(
                    price=price,
                    currency=(payload.get("currency") or currency).upper(),
                    carrier=row.get("airline", ""),
                    stops=transfers,
                    segments=[
                        {
                            "from": row.get("origin"),
                            "to": row.get("destination"),
                            "departure": row.get("departure_at"),
                        }
                    ],
                    layovers_known=False,  # 此端點不給中轉機場
                    booking_link=_full_link(row.get("link")),
                )
            )
        return offers


def _full_link(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else f"https://www.aviasales.com{path}"
