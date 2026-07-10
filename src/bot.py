"""Telegram bot：接收訊息、建立監控，並定時查價推播。"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

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
        ok = self.storage.deactivate_seq(update.effective_chat.id, watch_id)
        await update.message.reply_text(
            f"🗑️ 已刪除監控 #{watch_id}" if ok else f"找不到屬於你的監控 #{watch_id}"
        )

    async def cmd_chart(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from .chart import render_price_chart  # 延後 import，沒裝 matplotlib 也不影響其他指令

        chat_id = update.effective_chat.id
        watches = self.storage.list_watches(chat_id)
        if not watches:
            await update.message.reply_text("你還沒有任何監控喔。")
            return
        # /chart 3 指定某個；不給就畫全部
        if ctx.args and ctx.args[0].lstrip("#").isdigit():
            wid = int(ctx.args[0].lstrip("#"))
            watches = [w for w in watches if w.display_no == wid]
            if not watches:
                await update.message.reply_text(f"找不到屬於你的監控 #{wid}")
                return
        for w in watches:
            # 先即時查一次、記一筆現價，讓「連按 /chart」也能累積資料
            try:
                res = check_watch(
                    self.provider, w,
                    adults=self.config.adults,
                    good_deal_ratio=self.config.good_deal_ratio,
                    baseline_min_samples=self.config.baseline_min_samples,
                )
                if res.cheapest is not None:
                    self.storage.record_observation(w.id, res.cheapest.price)
            except FlightError as exc:
                logger.warning("畫圖前查價失敗 watch=%s：%s", w.id, exc)

            history = self.storage.get_history(w.id)
            if len(history) < 2:
                await update.message.reply_text(
                    f"監控 #{w.display_no} 已記錄一筆現價 👍 走勢圖至少要 2 筆，"
                    f"再按一次 /chart（或 /check）就能看圖了。"
                )
                continue
            baseline = w.price_sum / w.price_count if w.price_count else None
            png = render_price_chart(
                title=f"#{w.display_no} {w.origin}-{w.destination} {w.depart_date}",
                points=history, currency=w.currency,
                threshold=w.threshold, baseline=baseline,
            )
            await update.message.reply_photo(
                png, caption=f"#{w.display_no} {w.origin}→{w.destination} 價格走勢"
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
            time_filters=parsed.time_filters,
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

    async def _check_and_maybe_notify(self, ctx, watch, force_report: bool):
        try:
            result = check_watch(
                self.provider,
                watch,
                adults=self.config.adults,
                good_deal_ratio=self.config.good_deal_ratio,
                baseline_min_samples=self.config.baseline_min_samples,
            )
        except FlightError as exc:
            logger.warning("查價失敗 watch=%s：%s", watch.id, exc)
            if force_report:
                await ctx.bot.send_message(
                    watch.chat_id, f"⚠️ 監控 #{watch.display_no} 查價失敗，稍後會再試。"
                )
            return None

        if result.cheapest is not None:
            self.storage.record_observation(watch.id, result.cheapest.price)

        if result.should_notify and result.cheapest is not None:
            self.storage.mark_alerted(watch.id, result.cheapest.price)
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
                    f"監控 #{watch.display_no} 目前最低 {o.price:.0f} {o.currency}"
                    f"（{o.carrier}）。{result.reason}。",
                )
            else:
                await ctx.bot.send_message(
                    watch.chat_id, f"監控 #{watch.display_no}：{result.reason}。"
                )
        return result

    # ── 排程任務：每日摘要 ────────────────────────────────────────────────
    async def daily_digest(self, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        watches = self.storage.all_active_watches()
        results = {}
        for w in watches:
            results[w.id] = await self._check_and_maybe_notify(ctx, w, force_report=False)
        by_chat: dict = {}
        for w in watches:
            by_chat.setdefault(w.chat_id, []).append(w)
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")
        for chat_id, ws in by_chat.items():
            await ctx.bot.send_message(
                chat_id, messages.daily_digest(today, ws, results),
                parse_mode=ParseMode.HTML,
            )

    # ── 啟動 ──────────────────────────────────────────────────────────────
    def build_application(self) -> Application:
        app = Application.builder().token(self.config.telegram_token).build()
        app.add_handler(CommandHandler(["start", "help"], self.cmd_start))
        app.add_handler(CommandHandler("list", self.cmd_list))
        app.add_handler(CommandHandler("del", self.cmd_del))
        app.add_handler(CommandHandler("check", self.cmd_check))
        app.add_handler(CommandHandler("chart", self.cmd_chart))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message)
        )
        interval = self.config.check_interval_minutes * 60
        app.job_queue.run_repeating(
            self.scheduled_check, interval=interval, first=interval
        )
        # 每天台北時間 digest_hour 送一次摘要（UTC = 台北 - 8）
        app.job_queue.run_daily(
            self.daily_digest,
            time=time(hour=(self.config.digest_hour - 8) % 24),
        )
        return app

    def run(self) -> None:
        app = self.build_application()
        logger.info("Bot 啟動，每 %d 分鐘檢查一次。", self.config.check_interval_minutes)
        app.run_polling()
