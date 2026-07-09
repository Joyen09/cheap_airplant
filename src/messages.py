"""把資料轉成給使用者看的 Telegram 訊息文字。"""
from __future__ import annotations

from urllib.parse import quote

from .monitor import CheckResult
from .parser import ParsedWatch
from .storage import Watch


def _google_flights_url(w) -> str:
    """組一個「一開就已拉好搜尋條件」的 Google Flights 連結。

    用 fast-flights 產生 tfs 編碼連結（航線/日期/來回/幣別），再由 gflink
    把時間限制（幾點前/後）與轉機點也補進 tfs——一開頁全部條件都套好。
    沒裝套件或失敗時退回自然語言查詢格式。
    """
    try:
        import json

        from fast_flights import FlightQuery, Passengers, create_query

        from .gflink import augment_tfs

        legs = [FlightQuery(date=w.depart_date, from_airport=w.origin,
                            to_airport=w.destination)]
        ret = getattr(w, "return_date", None)
        if ret:
            legs.append(FlightQuery(date=ret, from_airport=w.destination,
                                    to_airport=w.origin))
        q = create_query(
            flights=legs,
            trip="round-trip" if ret else "one-way",
            passengers=Passengers(adults=1),
            currency=getattr(w, "currency", "") or "",
            language="zh-TW",
        )
        tfs = q.params()["tfs"]
        tf_raw = getattr(w, "time_filters", None)
        vias = w.via.split(",") if getattr(w, "via", None) else []
        tfs = augment_tfs(tfs, json.loads(tf_raw) if tf_raw else None, vias)
        cur = getattr(w, "currency", "") or ""
        return (
            "https://www.google.com/travel/flights/search"
            f"?tfs={tfs}&hl=zh-TW&curr={cur}"
        )
    except Exception:  # noqa: BLE001 - 連結產生失敗就退回舊格式
        q = f"flights from {w.origin} to {w.destination} on {w.depart_date}"
        if getattr(w, "return_date", None):
            q += f" returning {w.return_date}"
        return "https://www.google.com/travel/flights?q=" + quote(q)


def _booking_section(w, offer) -> str:
    lines = [f'🔗 <a href="{_google_flights_url(w)}">在 Google Flights 查看／訂票（含時間/轉機條件）</a>']
    if offer is not None and offer.booking_link:
        lines.append(f'　└ 或<a href="{offer.booking_link}">資料來源的訂票頁</a>')
    if offer is not None and offer.carrier:
        lines.append(f"　└ 也可直接到「{offer.carrier}」官網訂同班")
    return "\n".join(lines)

HELP_TEXT = (
    "✈️ <b>便宜機票通知機器人</b>\n\n"
    "直接傳訊息告訴我航線、日期跟預算，我就會幫你盯著價格，便宜了主動通知你。\n\n"
    "<b>範例</b>\n"
    "• 從 TPE 到 NRT 7/1 出發 7/10 回程 低於 12000\n"
    "• 台北 到 大阪 經 香港 來回 2026-07-01 ~ 2026-07-10\n"
    "• TPE -> KIX 8/15 單程\n"
    "• TPE 到 LHR 經 HKG 轉 DXB 9/1（多個轉乘點）\n"
    "• TPE 到 NRT 9/26 去程 09:00 後 回程 15:00 後（避開太早/太晚）\n"
    "　（時間可用 前 或 後，例如「去程 18:00 前」）\n\n"
    "<b>指令</b>\n"
    "/list — 看目前所有監控\n"
    "/del &lt;編號&gt; — 刪除某個監控\n"
    "/check — 立刻檢查一次所有監控\n"
    "/chart [編號] — 看價格走勢圖\n"
    "new — 用按鈕一步步建立監控，會先顯示目前行情（Discord 專用）\n"
    "/help — 顯示這份說明"
)


def _time_filter_label(w) -> str:
    tf_raw = getattr(w, "time_filters", None)
    if not tf_raw:
        return ""
    import json
    tf = json.loads(tf_raw)
    parts = []
    if tf.get("out_before"):
        parts.append(f"去程 {tf['out_before']} 前")
    if tf.get("out_after"):
        parts.append(f"去程 {tf['out_after']} 後")
    if tf.get("ret_before"):
        parts.append(f"回程 {tf['ret_before']} 前")
    if tf.get("ret_after"):
        parts.append(f"回程 {tf['ret_after']} 後")
    return "　🕒 " + "、".join(parts) if parts else ""


def _route_label(w) -> str:
    via = f" 經 {w.via.replace(',', '、')}" if getattr(w, "via", None) else ""
    trip = f" ↔ {w.return_date}" if getattr(w, "return_date", None) else "（單程）"
    return f"{w.origin} → {w.destination}{via}　{w.depart_date}{trip}{_time_filter_label(w)}"


def watch_created(w: Watch) -> str:
    budget = f"預算 {w.threshold:.0f} {w.currency}" if w.threshold else "無預算（創新低時通知）"
    return (
        "✅ <b>已建立監控</b>\n"
        f"航線：{_route_label(w)}\n"
        f"{budget}\n"
        f"編號 #{w.id}　我會定時幫你查價，便宜了就通知你 👀\n"
        f'🔗 <a href="{_google_flights_url(w)}">先看現在的價格／訂票</a>'
    )


def parse_failed(p: ParsedWatch) -> str:
    return f"🤔 {p.error}"


def list_watches(watches: list[Watch]) -> str:
    if not watches:
        return "目前沒有任何監控。傳一段航線給我就能開始，例如：『從 TPE 到 NRT 7/1 低於 12000』"
    lines = ["<b>目前的監控</b>"]
    for w in watches:
        budget = f"≤{w.threshold:.0f}" if w.threshold else "創新低"
        low = f"，最低看過 {w.lowest_seen:.0f}" if w.lowest_seen else ""
        lines.append(f"#{w.id}　{_route_label(w)}（{budget}{low}）")
    return "\n".join(lines)


def deal_alert(result: CheckResult) -> str:
    w = result.watch
    o = result.cheapest
    assert o is not None
    title = "🔥 <b>好價來了！</b>" if result.is_good_deal else "🔔 <b>便宜機票通知！</b>"
    return (
        f"{title}\n"
        f"航線：{_route_label(w)}\n"
        f"目前最低：<b>{o.price:.0f} {o.currency}</b>"
        f"（{o.carrier}，{'直飛' if o.stops == 0 else f'轉{o.stops}次'}）\n"
        f"原因：{result.reason}\n"
        f"監控 #{w.id}\n"
        f"{_booking_section(w, o)}"
    )


def daily_digest(date_str: str, watches: list[Watch], prices: dict) -> str:
    """每日摘要：就算沒觸發通知，也固定回報每個監控目前最低價。

    prices: {watch_id: CheckResult}，提供本次查到的現價與常態價。
    """
    lines = [f"📋 <b>每日機票摘要</b>（{date_str}）"]
    for w in watches:
        res = prices.get(w.id)
        if res is not None and res.cheapest is not None:
            o = res.cheapest
            now = f"目前最低 <b>{o.price:.0f} {w.currency}</b>（{o.carrier}）"
            extra = f"，常態約 {res.baseline:.0f}" if res.baseline else ""
        else:
            low = f"{w.lowest_seen:.0f}" if w.lowest_seen else "—"
            now = f"目前查無報價（看過最低 {low}）"
            extra = ""
        budget = f"，你的預算 {w.threshold:.0f}" if w.threshold else ""
        lines.append(f"#{w.id}　{_route_label(w)}\n　└ {now}{extra}{budget}")
    lines.append("\n要立刻重查可按 /check，管理用 /list、/del")
    return "\n".join(lines)
