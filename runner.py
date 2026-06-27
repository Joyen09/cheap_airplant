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

from src import messages
from src.amadeus_client import AmadeusError
from src.amadeus_client import AmadeusClient
from src.config import Config
from src.json_storage import JsonStorage
from src.monitor import check_watch
from src.parser import parse_message
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
            ok = store.deactivate(int(arg), chat_id)
            tg.send_message(
                chat_id,
                f"🗑️ 已刪除監控 #{arg}" if ok else f"找不到屬於你的監控 #{arg}",
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
        )
        tg.send_message(chat_id, messages.watch_created(watch))
        new_watch_ids.add(watch.id)

    return new_watch_ids, force_chats


def run_price_checks(store, tg, amadeus, config, new_watch_ids, force_chats) -> None:
    for watch in store.all_active_watches():
        force = watch.id in new_watch_ids or watch.chat_id in force_chats
        try:
            result = check_watch(
                amadeus, watch,
                adults=config.adults,
                new_low_ratio=config.new_low_notify_ratio,
            )
        except AmadeusError as exc:
            logger.warning("查價失敗 watch=%s：%s", watch.id, exc)
            if force:
                tg.send_message(
                    watch.chat_id,
                    f"⚠️ 監控 #{watch.id} 查價失敗，下次排程會再試。",
                    html=False,
                )
            continue

        if result.new_lowest is not None:
            store.update_lowest_seen(watch.id, result.new_lowest)

        if result.should_notify and result.cheapest is not None:
            tg.send_message(watch.chat_id, messages.deal_alert(result))
        elif force:
            if result.cheapest is not None:
                o = result.cheapest
                tg.send_message(
                    watch.chat_id,
                    f"監控 #{watch.id} 目前最低 {o.price:.0f} {o.currency}"
                    f"（{o.carrier}）。{result.reason}。",
                    html=False,
                )
            else:
                tg.send_message(
                    watch.chat_id, f"監控 #{watch.id}：{result.reason}。", html=False
                )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.load()
    state_path = os.getenv("STATE_PATH", "bot_state.json")

    store = JsonStorage(state_path)
    tg = TelegramAPI(config.telegram_token)
    amadeus = AmadeusClient(
        config.amadeus_client_id,
        config.amadeus_client_secret,
        config.amadeus_env,
    )

    new_watch_ids, force_chats = process_updates(store, tg)
    run_price_checks(store, tg, amadeus, config, new_watch_ids, force_chats)
    store.save()
    logger.info("這次執行完成，狀態已存到 %s", state_path)


if __name__ == "__main__":
    main()
