"""Telegram bot：接收訊息、建立監控，並定時查價推播。"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import messages
from .config import Config
from .flight_offer import FlightError
from .monitor import check_watch
from .parser import parse_message
from .providers import build_provider
from .storage import Storage

logger = logging.getLogger(__name__)


class FlightBot:
    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage(config.db_path)
        self.provider = build_provider(config)

    # ── 指令 ──────────────────────────────────────────────────────────────
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_html(messages.HELP_TEXT)

    async def cmd_list(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        watches = self.storage.list_watches(update.effective_chat.id)
        await update.message.reply_html(messages.list_watches(watches))

    async def cmd_del(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args or not ctx.args[0].lstrip("#").isdigit():
            await update.message.reply_text("用法：/del <編號>，例如 /del 3")
            return
        watch_id = int(ctx.args[0].lstrip("#"))
        ok = self.storage.deactivate(watch_id, update.effective_chat.id)
        await update.message.reply_text(
            f"🗑️ 已刪除監控 #{watch_id}" if ok else f"找不到屬於你的監控 #{watch_id}"
        )

    async def cmd_check(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        watches = self.storage.list_watches(chat_id)
        if not watches:
            await update.message.reply_text("你還沒有任何監控喔。")
            return
        await update.message.reply_text(f"🔍 正在檢查 {len(watches)} 個監控…")
        for w in watches:
            await self._check_and_maybe_notify(ctx, w, force_report=True)

    # ── 一般訊息 → 建立監控 ────────────────────────────────────────────────
    async def on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        parsed = parse_message(update.message.text)
        if not parsed.ok:
            await update.message.reply_text(messages.parse_failed(parsed))
            return
        watch = self.storage.add_watch(
            chat_id=update.effective_chat.id,
            origin=parsed.origin,
            destination=parsed.destination,
            via=parsed.via,
            depart_date=parsed.depart_date,
            return_date=parsed.return_date,
            threshold=parsed.threshold,
            currency=self.config.currency,
        )
        await update.message.reply_html(messages.watch_created(watch))
        # 馬上查一次給使用者一個基準價
        await self._check_and_maybe_notify(ctx, watch, force_report=True)

    # ── 排程任務：定時掃所有監控 ──────────────────────────────────────────
    async def scheduled_check(self, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        watches = self.storage.all_active_watches()
        logger.info("排程檢查 %d 個監控", len(watches))
        for w in watches:
            await self._check_and_maybe_notify(ctx, w, force_report=False)

    async def _check_and_maybe_notify(self, ctx, watch, force_report: bool) -> None:
        try:
            result = check_watch(
                self.provider,
                watch,
                adults=self.config.adults,
                new_low_ratio=self.config.new_low_notify_ratio,
            )
        except FlightError as exc:
            logger.warning("查價失敗 watch=%s：%s", watch.id, exc)
            if force_report:
                await ctx.bot.send_message(
                    watch.chat_id, f"⚠️ 監控 #{watch.id} 查價失敗，稍後會再試。"
                )
            return

        if result.new_lowest is not None:
            self.storage.update_lowest_seen(watch.id, result.new_lowest)

        if result.should_notify and result.cheapest is not None:
            await ctx.bot.send_message(
                watch.chat_id,
                messages.deal_alert(result),
                parse_mode=ParseMode.HTML,
            )
        elif force_report:
            if result.cheapest is not None:
                o = result.cheapest
                await ctx.bot.send_message(
                    watch.chat_id,
                    f"監控 #{watch.id} 目前最低 {o.price:.0f} {o.currency}"
                    f"（{o.carrier}）。{result.reason}。",
                )
            else:
                await ctx.bot.send_message(
                    watch.chat_id, f"監控 #{watch.id}：{result.reason}。"
                )

    # ── 啟動 ──────────────────────────────────────────────────────────────
    def build_application(self) -> Application:
        app = Application.builder().token(self.config.telegram_token).build()
        app.add_handler(CommandHandler(["start", "help"], self.cmd_start))
        app.add_handler(CommandHandler("list", self.cmd_list))
        app.add_handler(CommandHandler("del", self.cmd_del))
        app.add_handler(CommandHandler("check", self.cmd_check))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message)
        )
        interval = self.config.check_interval_minutes * 60
        app.job_queue.run_repeating(
            self.scheduled_check, interval=interval, first=interval
        )
        return app

    def run(self) -> None:
        app = self.build_application()
        logger.info("Bot 啟動，每 %d 分鐘檢查一次。", self.config.check_interval_minutes)
        app.run_polling()
