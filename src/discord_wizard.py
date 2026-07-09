"""Discord 按鈕/選單版「建立監控」精靈。

流程：
  1. [➕ 建立監控] 按鈕 → 表單（出發地/目的地/日期/預算）
  2. 送出後即時查價 → 摘要卡片顯示「目前最低、價格區間」與建議預算
  3. 下拉選單選去程/回程時段、按鈕設轉機點/預算 → ✅ 建立
"""
from __future__ import annotations

import asyncio
import logging

import discord

from . import messages
from .flight_offer import FlightError
from .wizard_logic import (
    TIME_PRESETS,
    Draft,
    apply_time_preset,
    parse_budget_input,
    parse_vias_input,
    price_context,
    suggest_budgets,
    summarize_draft,
    validate_core,
)

logger = logging.getLogger(__name__)


async def _fetch_context(bot, draft: Draft) -> dict | None:
    """即時查一次價，整理成行情摘要。查不到回 None。

    這裡攔所有例外（不只 FlightError）：deferred 互動若讓例外穿出去，
    使用者會永遠卡在「思考中」——查價失敗就降級成「暫時查不到報價」。
    """
    try:
        offers = await asyncio.to_thread(
            bot.provider.search_offers,
            origin=draft.origin,
            destination=draft.destination,
            depart_date=draft.depart_date,
            return_date=draft.return_date,
            adults=bot.config.adults,
            currency=bot.config.currency,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("精靈查價失敗：%s", exc)
        return None
    return price_context(offers)


def _render_embed(draft: Draft, ctx: dict | None, currency: str) -> discord.Embed:
    embed = discord.Embed(title="🛫 建立機票監控", colour=0x2563EB)
    embed.description = "\n".join(summarize_draft(draft))
    if ctx:
        stops = "直飛" if ctx["stops"] == 0 else f"轉{ctx['stops']}次"
        embed.add_field(
            name="📊 目前行情",
            value=(
                f"最低 **{ctx['low']:.0f} {ctx['currency']}**"
                f"（{ctx['carrier']}，{stops}）\n"
                f"中位數約 {ctx['median']:.0f}（{ctx['count']} 筆報價）"
            ),
            inline=False,
        )
        tips = " / ".join(label for label, _ in suggest_budgets(ctx["low"]))
        if tips:
            embed.add_field(name="💡 建議預算", value=tips, inline=False)
    else:
        embed.add_field(
            name="📊 目前行情",
            value="暫時查不到報價（仍可建立監控，之後查到會通知）",
            inline=False,
        )
    embed.set_footer(text="用下面的選單/按鈕調整條件，完成後按 ✅ 建立")
    return embed


class _TimeSelect(discord.ui.Select):
    def __init__(self, wizard: "SummaryView", leg: str, row: int):
        self._wizard = wizard
        self._leg = leg
        label = "去程時間" if leg == "out" else "回程時間"
        options = [
            discord.SelectOption(label=f"{label}：{text}", value=key)
            for key, (text, _, _) in TIME_PRESETS.items()
        ]
        super().__init__(placeholder=f"🕒 {label}（可不選）", options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        apply_time_preset(self._wizard.draft, self._leg, self.values[0])
        await self._wizard.refresh(interaction)


class _ViaModal(discord.ui.Modal, title="指定轉機點"):
    vias = discord.ui.TextInput(
        label="轉機機場（逗號分隔，留空=不限）",
        placeholder="例：香港, ICN",
        required=False,
    )

    def __init__(self, wizard: "SummaryView"):
        super().__init__()
        self._wizard = wizard
        if wizard.draft.vias:
            self.vias.default = ", ".join(wizard.draft.vias)

    async def on_submit(self, interaction: discord.Interaction):
        codes, bad = parse_vias_input(str(self.vias.value))
        self._wizard.draft.vias = codes
        if bad:
            await interaction.response.send_message(
                "看不懂這些轉機點（已略過）：" + "、".join(bad))
            await self._wizard.refresh(None)
        else:
            await self._wizard.refresh(interaction)


class _BudgetModal(discord.ui.Modal, title="設定預算"):
    budget = discord.ui.TextInput(label="預算金額（留空=不設）", required=False)

    def __init__(self, wizard: "SummaryView"):
        super().__init__()
        self._wizard = wizard
        ctx = wizard.ctx
        if wizard.draft.threshold:
            self.budget.default = f"{wizard.draft.threshold:.0f}"
        elif ctx:
            # 預填「比現價便宜 10%」的建議值
            tips = suggest_budgets(ctx["low"])
            if len(tips) >= 2:
                self.budget.default = f"{tips[1][1]:.0f}"

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.budget.value).strip()
        if not raw:
            self._wizard.draft.threshold = None
            await self._wizard.refresh(interaction)
            return
        value = parse_budget_input(raw)
        if value is None:  # 看不懂就保留原設定並提示，不靜默清掉
            await interaction.response.send_message(
                f"看不懂預算「{raw}」（填數字即可），已保留原本的設定。")
            return
        self._wizard.draft.threshold = value
        await self._wizard.refresh(interaction)


class SummaryView(discord.ui.View):
    """摘要卡片：時段選單 + 轉機/預算/建立/取消按鈕。"""

    def __init__(self, bot, draft: Draft, ctx: dict | None):
        super().__init__(timeout=600)
        self.bot = bot
        self.draft = draft
        self.ctx = ctx
        self.message: discord.Message | None = None
        self._finished = False  # 防連點：建立/取消只允許執行一次
        self.add_item(_TimeSelect(self, "out", row=0))
        if draft.return_date:
            self.add_item(_TimeSelect(self, "ret", row=1))

    async def refresh(self, interaction: discord.Interaction | None):
        embed = _render_embed(self.draft, self.ctx, self.bot.config.currency)
        try:
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            elif self.message is not None:
                # followup 訊息的編輯走互動 token（15 分鐘失效），過期就放棄更新畫面
                await self.message.edit(embed=embed, view=self)
        except discord.HTTPException as exc:
            logger.warning("更新精靈卡片失敗（可能 token 過期）：%s", exc)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="✈️ 轉機點", style=discord.ButtonStyle.secondary, row=2)
    async def via_btn(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(_ViaModal(self))

    @discord.ui.button(label="💰 預算", style=discord.ButtonStyle.secondary, row=2)
    async def budget_btn(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(_BudgetModal(self))

    @discord.ui.button(label="✅ 建立", style=discord.ButtonStyle.success, row=2)
    async def create_btn(self, interaction: discord.Interaction, _):
        if self._finished:  # 防連點：第二次點擊直接吞掉
            await interaction.response.defer()
            return
        self._finished = True
        draft = self.draft
        watch = self.bot.storage.add_watch(
            chat_id=interaction.channel.id,
            origin=draft.origin, destination=draft.destination,
            via=draft.via_str,
            depart_date=draft.depart_date, return_date=draft.return_date,
            threshold=draft.threshold, currency=self.bot.config.currency,
            time_filters=draft.time_filters_json,
        )
        # 只有在「沒設轉機/時間條件」時，才用行情最低價當第一筆基準觀測——
        # 有條件時全市場最低價可能是符合條件航班永遠達不到的數字，會污染基準。
        if self.ctx and not draft.vias and not draft.time_filters:
            self.bot.storage.record_observation(watch.id, self.ctx["low"])
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        from .discord_bot import _to_discord
        await interaction.followup.send(_to_discord(messages.watch_created(watch)))
        self.stop()

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.danger, row=2)
    async def cancel_btn(self, interaction: discord.Interaction, _):
        if self._finished:
            await interaction.response.defer()
            return
        self._finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="已取消，沒有建立監控。", view=self)
        self.stop()


class WatchModal(discord.ui.Modal, title="建立機票監控"):
    origin = discord.ui.TextInput(label="出發地（TPE 或 台北）", max_length=20)
    destination = discord.ui.TextInput(label="目的地（NRT 或 東京）", max_length=20)
    depart = discord.ui.TextInput(label="去程日期（9/26 或 2026-09-26）", max_length=12)
    ret = discord.ui.TextInput(label="回程日期（留空＝單程）", required=False, max_length=12)
    budget = discord.ui.TextInput(label="預算（留空＝之後再設）", required=False, max_length=10)

    def __init__(self, bot):
        super().__init__()
        self._bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        draft, errors = validate_core(
            str(self.origin.value), str(self.destination.value),
            str(self.depart.value), str(self.ret.value), str(self.budget.value),
        )
        if errors:
            await interaction.response.send_message(
                "🤔 " + "\n".join(errors), view=StartView(self._bot))
            return
        await interaction.response.defer(thinking=True)
        ctx = await _fetch_context(self._bot, draft)
        view = SummaryView(self._bot, draft, ctx)
        embed = _render_embed(draft, ctx, self._bot.config.currency)
        view.message = await interaction.followup.send(embed=embed, view=view)


class StartView(discord.ui.View):
    """常駐入口按鈕：timeout=None + 固定 custom_id = persistent view，
    配合 on_ready 的 bot.add_view()，重啟後舊訊息上的按鈕也照常可用。"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self._bot = bot

    @discord.ui.button(label="➕ 建立監控", style=discord.ButtonStyle.primary,
                       custom_id="flight_wizard:start")
    async def start(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(WatchModal(self._bot))
