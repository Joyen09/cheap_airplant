"""一次性執行：給 GitHub Actions 定時呼叫。

每次跑會做三件事：
  1. 讀取新的 Telegram 訊息 → 建立 / 管理監控並回覆
  2. 幫所有監控查價 → 便宜就主動通知
  3. 把狀態存回 JSON（由 workflow 提交回 repo 永久保留）

本地測試：填好 .env 後直接 `python runner.py`。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from src import messages
from src.config import Config
from src.flight_offer import FlightError
from src.json_storage import JsonStorage
from src.monitor import check_watch
from src.parser import parse_message
from src.providers import build_provider
from src.telegram_api import TelegramAPI

logger = logging.getLogger(__name__)


def _handle_command(text, chat_id, store, tg) -> bool:
    """處理 / 指令。回傳 True 表示這則訊息已被當成指令處理。"""
    cmd, *rest = text.strip().split(maxsplit=1)
    cmd = cmd.lower().split("@")[0]  # 去掉群組裡的 @botname

    if cmd in ("/start", "/help"):
        tg.send_message(chat_id, messages.HELP_TEXT)
    elif cmd == "/list":
        tg.send_message(chat_id, messages.list_watches(store.list_watches(chat_id)))
    elif cmd == "/del":
        arg = (rest[0] if rest else "").lstrip("#").strip()
        if not arg.isdigit():
            tg.send_message(chat_id, "用法：/del <編號>，例如 /del 3", html=False)
        else:
            ok = store.deactivate_seq(chat_id, int(arg))
            tg.send_message(
                chat_id,
                f"🗑️ 已刪除監控 #{arg}" if ok else f"找不到屬於你的監控 #{arg}",
                html=False,
            )
    elif cmd == "/chart":
        tg.send_message(
            chat_id,
            "📈 走勢圖功能需在常駐主機模式（GCP VM）才支援，目前這個排程模式無法傳圖。",
            html=False,
        )
    else:
        return False
    return True


def process_updates(store: JsonStorage, tg: TelegramAPI) -> tuple[set[int], set[int]]:
    """讀新訊息、建立監控。回傳 (要立即回報的 watch id, 要立即回報的 chat id)。"""
    new_watch_ids: set[int] = set()
    force_chats: set[int] = set()

    try:
        updates = tg.get_updates(offset=store.last_update_id + 1)
    except Exception as exc:  # noqa: BLE001 - CI 上不要因為一次失敗整個掛掉
        logger.warning("讀取 Telegram 訊息失敗：%s", exc)
        return new_watch_ids, force_chats

    for upd in updates:
        store.last_update_id = max(store.last_update_id, upd["update_id"])
        msg = upd.get("message")
        if not msg or "text" not in msg:
            continue
        chat_id = msg["chat"]["id"]
        text = msg["text"]

        if text.strip().startswith("/"):
            cmd = text.strip().split()[0].lower().split("@")[0]
            if cmd == "/check":
                force_chats.add(chat_id)
                tg.send_message(chat_id, "🔍 這就幫你查一次。", html=False)
                continue
            if _handle_command(text, chat_id, store, tg):
                continue

        parsed = parse_message(text)
        if not parsed.ok:
            tg.send_message(chat_id, messages.parse_failed(parsed), html=False)
            continue
        watch = store.add_watch(
            chat_id=chat_id,
            origin=parsed.origin,
            destination=parsed.destination,
            via=parsed.via,
            depart_date=parsed.depart_date,
            return_date=parsed.return_date,
            threshold=parsed.threshold,
            currency=os.getenv("CURRENCY", "TWD"),
            time_filters=parsed.time_filters,
        )
        tg.send_message(chat_id, messages.watch_created(watch))
        new_watch_ids.add(watch.id)

    return new_watch_ids, force_chats


def run_price_checks(store, tg, provider, config, new_watch_ids, force_chats) -> dict:
    """查所有監控的價。回傳 {watch_id: CheckResult}（給每日摘要用）。"""
    results: dict = {}
    for watch in store.all_active_watches():
        force = watch.id in new_watch_ids or watch.chat_id in force_chats
        try:
            result = check_watch(
                provider, watch,
                adults=config.adults,
                good_deal_ratio=config.good_deal_ratio,
                baseline_min_samples=config.baseline_min_samples,
            )
        except FlightError as exc:
            logger.warning("查價失敗 watch=%s：%s", watch.id, exc)
            if force:
                tg.send_message(
                    watch.chat_id,
                    f"⚠️ 監控 #{watch.display_no} 查價失敗，下次排程會再試。",
                    html=False,
                )
            continue

        results[watch.id] = result
        # 先記錄這次觀測（更新歷史最低與常態價統計）
        if result.cheapest is not None:
            store.record_observation(watch.id, result.cheapest.price)

        if result.should_notify and result.cheapest is not None:
            store.mark_alerted(watch.id, result.cheapest.price)
            tg.send_message(watch.chat_id, messages.deal_alert(result))
        elif force:
            if result.cheapest is not None:
                o = result.cheapest
                tg.send_message(
                    watch.chat_id,
                    f"監控 #{watch.display_no} 目前最低 {o.price:.0f} {o.currency}"
                    f"（{o.carrier}）。{result.reason}。",
                    html=False,
                )
            else:
                tg.send_message(
                    watch.chat_id, f"監控 #{watch.display_no}：{result.reason}。", html=False
                )
    return results


def maybe_send_digest(store, tg, config, results) -> None:
    """每天一次（台北時間 digest_hour 之後的第一次執行）送出摘要。"""
    now_tw = datetime.now(timezone.utc) + timedelta(hours=8)
    today = now_tw.strftime("%Y-%m-%d")
    if store.last_digest_date == today or now_tw.hour < config.digest_hour:
        return

    by_chat: dict = {}
    for w in store.all_active_watches():
        by_chat.setdefault(w.chat_id, []).append(w)
    for chat_id, watches in by_chat.items():
        tg.send_message(chat_id, messages.daily_digest(today, watches, results))
    store.last_digest_date = today
    logger.info("已送出每日摘要給 %d 個聊天室", len(by_chat))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.load()
    state_path = os.getenv("STATE_PATH", "bot_state.json")

    store = JsonStorage(state_path)
    tg = TelegramAPI(config.telegram_token)
    provider = build_provider(config)
    logger.info("使用資料來源：%s", provider.name)

    new_watch_ids, force_chats = process_updates(store, tg)
    results = run_price_checks(store, tg, provider, config, new_watch_ids, force_chats)
    maybe_send_digest(store, tg, config, results)
    store.save()
    logger.info("這次執行完成，狀態已存到 %s", state_path)


if __name__ == "__main__":
    main()
