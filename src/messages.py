"""把資料轉成給使用者看的 Telegram 訊息文字。"""
from __future__ import annotations

from .monitor import CheckResult
from .parser import ParsedWatch
from .storage import Watch

HELP_TEXT = (
    "✈️ <b>便宜機票通知機器人</b>\n\n"
    "直接傳訊息告訴我航線、日期跟預算，我就會幫你盯著價格，便宜了主動通知你。\n\n"
    "<b>範例</b>\n"
    "• 從 TPE 到 NRT 7/1 出發 7/10 回程 低於 12000\n"
    "• 台北 到 大阪 經 香港 來回 2026-07-01 ~ 2026-07-10\n"
    "• TPE -> KIX 8/15 單程\n\n"
    "<b>指令</b>\n"
    "/list — 看目前所有監控\n"
    "/del &lt;編號&gt; — 刪除某個監控\n"
    "/check — 立刻檢查一次所有監控\n"
    "/help — 顯示這份說明"
)


def _route_label(w) -> str:
    via = f" 經 {w.via}" if getattr(w, "via", None) else ""
    trip = f" ↔ {w.return_date}" if getattr(w, "return_date", None) else "（單程）"
    return f"{w.origin} → {w.destination}{via}　{w.depart_date}{trip}"


def watch_created(w: Watch) -> str:
    budget = f"預算 {w.threshold:.0f} {w.currency}" if w.threshold else "無預算（創新低時通知）"
    return (
        "✅ <b>已建立監控</b>\n"
        f"航線：{_route_label(w)}\n"
        f"{budget}\n"
        f"編號 #{w.id}　我會定時幫你查價，便宜了就通知你 👀"
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
    return (
        "🔥 <b>便宜機票通知！</b>\n"
        f"航線：{_route_label(w)}\n"
        f"目前最低：<b>{o.price:.0f} {o.currency}</b>"
        f"（{o.carrier}，{'直飛' if o.stops == 0 else f'轉{o.stops}次'}）\n"
        f"原因：{result.reason}\n"
        f"監控 #{w.id}"
    )
