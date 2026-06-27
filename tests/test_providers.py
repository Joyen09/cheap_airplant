import pytest

from src.flight_offer import QuotaExceeded
from src.providers.fallback import FallbackProvider
from src.providers.serpapi import SerpApiClient
from src.providers.travelpayouts import TravelpayoutsClient


# ── Travelpayouts 解析 ───────────────────────────────────────────────────────
def test_travelpayouts_parse():
    payload = {
        "currency": "twd",
        "data": [
            {"origin": "TPE", "destination": "NRT", "price": 8500,
             "airline": "JX", "transfers": 0, "departure_at": "2026-07-01T08:00:00Z",
             "link": "/search/TPE0107NRT1"},
            {"origin": "TPE", "destination": "NRT", "price": 7200,
             "airline": "CI", "transfers": 1, "departure_at": "2026-07-01T10:00:00Z"},
        ],
    }
    offers = TravelpayoutsClient._parse(payload, "twd")
    assert len(offers) == 2
    assert offers[0].price == 8500
    assert offers[0].currency == "TWD"
    assert offers[0].booking_link.startswith("https://www.aviasales.com/")
    # 此來源不給中轉機場
    assert offers[1].layovers_known is False
    assert offers[1].stops == 1


def test_travelpayouts_via_is_best_effort():
    # 沒中轉機場資訊時：有轉乘的視為「可能經過」，直飛則排除
    payload = {"currency": "twd", "data": [
        {"origin": "TPE", "destination": "NRT", "price": 7000, "transfers": 1},
        {"origin": "TPE", "destination": "NRT", "price": 6000, "transfers": 0},
    ]}
    offers = TravelpayoutsClient._parse(payload, "twd")
    assert offers[0].goes_via("HKG") is True   # 有轉乘 → 不排除
    assert offers[1].goes_via("HKG") is False  # 直飛 → 一定沒經過


# ── SerpApi 解析 ─────────────────────────────────────────────────────────────
def test_serpapi_parse_with_segments():
    data = {
        "best_flights": [{
            "price": 9300,
            "flights": [
                {"departure_airport": {"id": "TPE", "time": "2026-07-01 08:00"},
                 "arrival_airport": {"id": "HKG", "time": "2026-07-01 10:00"},
                 "airline": "Cathay"},
                {"departure_airport": {"id": "HKG", "time": "2026-07-01 12:00"},
                 "arrival_airport": {"id": "NRT", "time": "2026-07-01 16:00"},
                 "airline": "Cathay"},
            ],
        }],
        "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights/x"},
    }
    offers = SerpApiClient._parse(data, "TWD")
    assert len(offers) == 1
    assert offers[0].price == 9300
    assert offers[0].stops == 1
    assert offers[0].layovers_known is True
    # 含完整中轉機場 → via 可精準判斷
    assert offers[0].goes_via("HKG") is True
    assert offers[0].goes_via("ICN") is False


# ── 自動 fallback ────────────────────────────────────────────────────────────
class _Boom:
    name = "boom"

    def search_offers(self, **kw):
        raise QuotaExceeded("用完了")


class _Stub:
    name = "stub"

    def __init__(self, offers):
        self._offers = offers

    def search_offers(self, **kw):
        return self._offers


def test_fallback_switches_on_quota():
    fb = FallbackProvider(primary=_Boom(), fallback=_Stub(["ok"]))
    assert fb.search_offers(origin="TPE", destination="NRT",
                            depart_date="2026-07-01") == ["ok"]


def test_fallback_uses_primary_when_ok():
    fb = FallbackProvider(primary=_Stub(["primary"]), fallback=_Stub(["fb"]))
    assert fb.search_offers() == ["primary"]
