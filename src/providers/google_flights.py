"""Google Flights 資料來源（透過 fast-flights 套件，免費、不需 API key）。

即時價、原生多幣別（含 TWD）、含完整轉乘機場與起飛時刻 → via 與時間過濾皆精準。
非官方管道（解析 Google Flights 頁面），若 Google 改版可能暫時失效——
失效時鏈上的備援來源（SerpApi / Travelpayouts）會自動接手。
"""
from __future__ import annotations

from ..flight_offer import FlightError, FlightOffer

_SUPPORTED_CURRENCIES = {
    "TWD", "USD", "EUR", "JPY", "KRW", "HKD", "GBP", "AUD", "CAD", "SGD",
    "THB", "CNY", "MYR", "IDR", "PHP", "VND", "INR", "NZD", "CHF",
}


def _fmt_dt(sdt) -> str:
    """SimpleDatetime(date=(y,m,d), time=(h,mi)) → 'YYYY-MM-DD HH:MM'。"""
    try:
        y, mo, d = sdt.date
        h, mi = sdt.time
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    except Exception:  # noqa: BLE001 - 寧可缺時刻也不要整筆丟掉
        return ""


class GoogleFlightsClient:
    name = "google"

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
        # 延後 import：沒裝 fast-flights 時其他來源照常運作
        try:
            from fast_flights import FlightQuery, Passengers, create_query, get_flights
            from fast_flights.exceptions import FlightsNotFound
        except ImportError as exc:
            raise FlightError(f"fast-flights 未安裝：{exc}") from exc

        legs = [FlightQuery(date=depart_date, from_airport=origin,
                            to_airport=destination)]
        if return_date:
            legs.append(FlightQuery(date=return_date, from_airport=destination,
                                    to_airport=origin))
        cur = currency.upper()
        query = create_query(
            flights=legs,
            trip="round-trip" if return_date else "one-way",
            passengers=Passengers(adults=adults),
            currency=cur if cur in _SUPPORTED_CURRENCIES else "",
        )
        try:
            results = get_flights(query)
        except FlightsNotFound as exc:
            raise FlightError(f"Google Flights 查無結果：{exc}") from exc
        except Exception as exc:  # noqa: BLE001 - 網路/解析失敗都交給備援
            raise FlightError(f"Google Flights 查詢失敗：{exc}") from exc

        return self._parse(list(results)[:max_results], cur)

    @staticmethod
    def _parse(results: list, currency: str) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        for item in results:
            try:
                price = float(item.price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            segments = [
                {
                    "from": leg.from_airport.code,
                    "to": leg.to_airport.code,
                    "departure": _fmt_dt(leg.departure),
                }
                for leg in (item.flights or [])
            ]
            offers.append(
                FlightOffer(
                    price=price,
                    currency=currency,
                    carrier=(item.airlines or [""])[0],
                    stops=max(0, len(segments) - 1),
                    segments=segments,
                    layovers_known=True,
                    booking_link=None,  # 通知本身已附 Google Flights 連結
                )
            )
        return offers
