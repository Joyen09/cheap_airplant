"""Discord bot：功能與 Telegram 版一模一樣，共用同一套核心邏輯。

在 DM（私訊）裡直接對話即可；在伺服器頻道裡則需以 `!` 開頭或 @提及機器人。
指令：help / list / del <編號> / check / chart [編號]（可加不加 `/`、`!` 前綴）。
其餘訊息一律當成「建立監控」的航線描述。
"""
from __future__ import annotations

import io
import logging
import re
from datetime import time as dtime
from datetime import timedelta, timezone

import discord
from discord.ext import tasks

from . import messages
from .config import Config
from .flight_offer import FlightError
from .monitor import check_watch
from .parser import parse_message
from .providers import build_provider
from .storage import Storage

logger = logging.getLogger(__name__)

_COMMANDS = {"help", "start", "list", "del", "check", "chart"}


def _to_discord(text: str) -> str:
    """把 messages 產生的 Telegram HTML 轉成 Discord 能顯示的格式。"""
    text = text.replace("<b>", "**").replace("</b>", "**")
    # <a href="URL">文字</a> → 文字：URL（Discord 一般訊息會把裸網址變成連結）
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r"\2：\1", text)
    return text


class FlightDiscordBot:
    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage(config.db_path)
        self.provider = build_provider(config)

        intents = discord.Intents.default()
        intents.message_content = True  # 需在開發者後台開啟 Message Content Intent
        self.bot = discord.Client(intents=intents)

        # 背景排程：定時查價 + 每天摘要（台北 digest_hour = UTC digest_hour-8）
        self._sched_loop = tasks.loop(minutes=config.check_interval_minutes)(
            self._do_scheduled
        )
        self._digest_loop = tasks.loop(
            time=dtime(hour=(config.digest_hour - 8) % 24, tzinfo=timezone.utc)
        )(self._do_digest)

        self._register()

    # ── 事件註冊 ──────────────────────────────────────────────────────────
    def _register(self) -> None:
        bot = self.bot

        @bot.event
        async def on_ready():
            logger.info("Discord bot 已登入：%s", bot.user)
            if not self._sched_loop.is_running():
                self._sched_loop.start()
            if not self._digest_loop.is_running():
                self._digest_loop.start()

        @bot.event
        async def on_message(msg: discord.Message):
            if msg.author == bot.user or msg.author.bot:
                return
            content = (msg.content or "").strip()
            if not content:
                return
            # 伺服器頻道：需 ! 開頭或提及機器人；DM 則直接回應
            if msg.guild is not None:
                if bot.user in msg.mentions:
                    content = content.replace(f"<@{bot.user.id}>", "").strip()
                elif content.startswith("!"):
                    content = content[1:].strip()
                else:
                    return
            await self._handle(msg, content)

    # ── 訊息處理 ──────────────────────────────────────────────────────────
    async def _handle(self, msg: discord.Message, content: str) -> None:
        head, *rest = content.split(maxsplit=1)
        cmd = head.lstrip("/!").lower()
        arg = rest[0] if rest else ""

        if cmd in ("help", "start"):
            await self._reply(msg, messages.HELP_TEXT)
        elif cmd == "list":
            await self._reply(msg, messages.list_watches(
                self.storage.list_watches(msg.channel.id)))
        elif cmd == "del":
            await self._cmd_del(msg, arg)
        elif cmd == "check":
            await self._cmd_check(msg)
        elif cmd == "chart":
            await self._cmd_chart(msg, arg)
        else:
            await self._cmd_new_watch(msg, content)

    async def _cmd_del(self, msg, arg) -> None:
        arg = arg.lstrip("#").strip()
        if not arg.isdigit():
            await msg.channel.send("用法：del <編號>，例如 del 3")
            return
        ok = self.storage.deactivate(int(arg), msg.channel.id)
        await msg.channel.send(
            f"🗑️ 已刪除監控 #{arg}" if ok else f"找不到屬於你的監控 #{arg}")

    async def _cmd_check(self, msg) -> None:
        watches = self.storage.list_watches(msg.channel.id)
        if not watches:
            await msg.channel.send("你還沒有任何監控喔。")
            return
        await msg.channel.send(f"🔍 正在檢查 {len(watches)} 個監控…")
        for w in watches:
            await self._check_one(w, force=True)

    async def _cmd_chart(self, msg, arg) -> None:
        from .chart import render_price_chart

        watches = self.storage.list_watches(msg.channel.id)
        if not watches:
            await msg.channel.send("你還沒有任何監控喔。")
            return
        if arg and arg.lstrip("#").isdigit():
            wid = int(arg.lstrip("#"))
            watches = [w for w in watches if w.id == wid]
            if not watches:
                await msg.channel.send(f"找不到屬於你的監控 #{wid}")
                return
        for w in watches:
            try:  # 先即時記一筆，讓連按也能累積
                res = check_watch(
                    self.provider, w, adults=self.config.adults,
                    good_deal_ratio=self.config.good_deal_ratio,
                    baseline_min_samples=self.config.baseline_min_samples)
                if res.cheapest is not None:
                    self.storage.record_observation(w.id, res.cheapest.price)
            except FlightError as exc:
                logger.warning("畫圖前查價失敗 watch=%s：%s", w.id, exc)
            history = self.storage.get_history(w.id)
            if len(history) < 2:
                await msg.channel.send(
                    f"監控 #{w.id} 已記錄一筆現價 👍 走勢圖至少要 2 筆，"
                    f"再按一次 chart（或 check）就能看圖了。")
                continue
            baseline = w.price_sum / w.price_count if w.price_count else None
            png = render_price_chart(
                title=f"#{w.id} {w.origin}-{w.destination} {w.depart_date}",
                points=history, currency=w.currency,
                threshold=w.threshold, baseline=baseline)
            await msg.channel.send(
                file=discord.File(io.BytesIO(png), filename=f"chart_{w.id}.png"))

    async def _cmd_new_watch(self, msg, content) -> None:
        parsed = parse_message(content)
        if not parsed.ok:
            await msg.channel.send(_to_discord(messages.parse_failed(parsed)))
            return
        watch = self.storage.add_watch(
            chat_id=msg.channel.id,
            origin=parsed.origin, destination=parsed.destination, via=parsed.via,
            depart_date=parsed.depart_date, return_date=parsed.return_date,
            threshold=parsed.threshold, currency=self.config.currency,
            time_filters=parsed.time_filters,
        )
        await self._reply(msg, messages.watch_created(watch))
        await self._check_one(watch, force=True)

    # ── 查價 / 通知 ───────────────────────────────────────────────────────
    async def _check_one(self, watch, force: bool):
        try:
            res = check_watch(
                self.provider, watch, adults=self.config.adults,
                good_deal_ratio=self.config.good_deal_ratio,
                baseline_min_samples=self.config.baseline_min_samples)
        except FlightError as exc:
            logger.warning("查價失敗 watch=%s：%s", watch.id, exc)
            if force:
                await self._send(watch.chat_id,
                                  f"⚠️ 監控 #{watch.id} 查價失敗，稍後會再試。")
            return None

        if res.cheapest is not None:
            self.storage.record_observation(watch.id, res.cheapest.price)

        if res.should_notify and res.cheapest is not None:
            self.storage.mark_alerted(watch.id, res.cheapest.price)
            await self._send(watch.chat_id, messages.deal_alert(res))
        elif force:
            if res.cheapest is not None:
                o = res.cheapest
                await self._send(
                    watch.chat_id,
                    f"監控 #{watch.id} 目前最低 {o.price:.0f} {o.currency}"
                    f"（{o.carrier}）。{res.reason}。")
            else:
                await self._send(watch.chat_id, f"監控 #{watch.id}：{res.reason}。")
        return res

    async def _do_scheduled(self) -> None:
        watches = self.storage.all_active_watches()
        logger.info("排程檢查 %d 個監控", len(watches))
        for w in watches:
            await self._check_one(w, force=False)

    async def _do_digest(self) -> None:
        watches = self.storage.all_active_watches()
        results = {}
        for w in watches:
            results[w.id] = await self._check_one(w, force=False)
        by_chat: dict = {}
        for w in watches:
            by_chat.setdefault(w.chat_id, []).append(w)
        today = (discord.utils.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
        for chat_id, ws in by_chat.items():
            await self._send(chat_id, messages.daily_digest(today, ws, results))

    # ── 傳送 ──────────────────────────────────────────────────────────────
    async def _reply(self, msg, text: str) -> None:
        await msg.channel.send(_to_discord(text))

    async def _send(self, chat_id: int, text: str) -> None:
        channel = self.bot.get_channel(chat_id)
        if channel is None:
            channel = await self.bot.fetch_channel(chat_id)
        await channel.send(_to_discord(text))

    # ── 啟動 ──────────────────────────────────────────────────────────────
    def run(self) -> None:
        logger.info("Discord bot 啟動中…")
        self.bot.run(self.config.discord_token)
