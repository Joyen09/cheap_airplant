from types import SimpleNamespace

from src.flight_offer import QuotaExceeded
from src.providers import build_provider
from src.providers.fallback import FallbackProvider
from src.providers.google_flights import GoogleFlightsClient


def _leg(frm, to, h=8, mi=30):
    return SimpleNamespace(
        from_airport=SimpleNamespace(code=frm, name=frm),
        to_airport=SimpleNamespace(code=to, name=to),
        departure=SimpleNamespace(date=(2026, 9, 18), time=(h, mi)),
        arrival=SimpleNamespace(date=(2026, 9, 18), time=(h + 2, mi)),
        duration=120,
        plane_type="A350",
    )


def _flights(price, legs, airlines=("Cathay",)):
    return SimpleNamespace(
        type="round-trip", price=price, airlines=list(airlines),
        flights=legs, carbon=None,
    )


def test_parse_maps_fields_and_segments():
    results = [
        _flights(9800, [_leg("HKG", "TPE")]),
        _flights(8700, [_leg("HKG", "NRT", h=6), _leg("NRT", "TPE", h=12)]),
    ]
    offers = GoogleFlightsClient._parse(results, "TWD")
    assert len(offers) == 2
    assert offers[0].price == 9800
    assert offers[0].currency == "TWD"
    assert offers[0].stops == 0
    assert offers[0].carrier == "Cathay"
    # 轉機那筆：有完整中轉機場與時刻 → via/時間過濾可精準運作
    assert offers[1].stops == 1
    assert offers[1].layovers_known is True
    assert offers[1].goes_via("NRT") is True
    assert offers[1].segments[0]["departure"] == "2026-09-18 06:30"


def test_parse_skips_zero_price():
    offers = GoogleFlightsClient._parse([_flights(0, [_leg("A", "B")])], "TWD")
    assert offers == []


def _cfg(serp="", tp=""):
    return SimpleNamespace(serpapi_key=serp, travelpayouts_token=tp)


def test_chain_google_only():
    p = build_provider(_cfg())
    assert isinstance(p, GoogleFlightsClient)


def test_chain_google_serp_tp_order():
    p = build_provider(_cfg(serp="k", tp="t"))
    # google -> (serpapi -> travelpayouts)
    assert p.primary.name == "google"
    assert p.fallback.primary.name == "serpapi"
    assert p.fallback.fallback.name == "travelpayouts"


def test_nested_last_used_propagates():
    class Boom:
        name = "boom"
        def search_offers(self, **kw):
            raise QuotaExceeded("out")

    class Ok:
        name = "ok"
        def search_offers(self, **kw):
            return ["x"]

    chain = FallbackProvider(primary=Boom(),
                             fallback=FallbackProvider(primary=Boom(), fallback=Ok()))
    assert chain.search_offers() == ["x"]
    assert chain.last_used == "ok"   # 穿透巢狀，回報實際供資料的來源
