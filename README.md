# ✈️ 便宜機票通知機器人 (cheap_airplant)

透過 **Telegram 或 Discord** 監控機票價格：你傳一段訊息說「從哪到哪、要不要轉乘、
什麼日期、預算多少」，機器人就會定時幫你查價，**便宜了或創新低就主動推播通知**給你。
兩個平台功能完全一樣（共用同一套核心邏輯）：Telegram 跑 `main.py`、Discord 跑
`main_discord.py`，設定見 **[deploy/DISCORD.md](deploy/DISCORD.md)**。

機票資料來源可插拔，依序自動 fallback：
**Google Flights（fast-flights，免費、即時、免金鑰）→ SerpApi（可選）→ Travelpayouts（可選）**。
主力 Google Flights 不需要任何 API key；後兩個是備援，設不設都能跑。
（原本的 Amadeus 自助版 API 已於 2026/7 停用，已改用上述來源。）

## 功能

- 📩 **自然語言建立監控**：傳 `從 TPE 到 NRT 經 HKG 7/1 出發 7/10 回程 低於 12000` 即可。
- 🖱️ **按鈕式建立（Discord）**：打 `new` 用表單+選單一步步填，送出前**先顯示目前行情**
  （最低價/中位數）與建議預算，選好時段/轉機點再確認建立。
- 🔁 **轉乘點過濾**：指定「經 X」時只比較有經過該機場的航班（SerpApi 精準；Travelpayouts 因不提供中轉機場，為盡力而為）。
- ⏰ **定時自動查價**：GitHub Actions 每 5 分鐘掃一次（本機模式預設每 60 分鐘，可調）。
- 🔔 **三種通知條件**：① 低於你設的預算；② 破歷史新低；③ 明顯低於這條航線「常態價」的好價 🔥。
- 🤫 **不重複轟炸**：同一個條件只有在「比上次通知更便宜」時才會再通知。
- 📋 **每日摘要**：每天固定回報一次各監控目前最低價，沒觸發也不讓你空等。
- 🗂️ **多監控管理**：`/list`、`/del`、`/check`。

## 兩種跑法

### A. 全程在 GitHub 上跑（推薦，免下載、免伺服器）

靠 **GitHub Actions** 每 5 分鐘自動執行一次：讀你傳的新訊息、查價、便宜就通知，
狀態存回 repo 裡的 `bot_state.json`。你完全不用開電腦。

> 💰 費用：公開 repo 的 GitHub Actions 免費且無限制。Travelpayouts 不按次計費、高頻查詢也免費；
> SerpApi 免費額度約 100 次/月，5 分鐘排程會很快用完，用完後會自動退回 Travelpayouts。

設定步驟（都在瀏覽器完成）：

1. 這個 repo 的 **Settings → Secrets and variables → Actions → New repository secret**，
   新增 secret：
   - `TELEGRAM_BOT_TOKEN`（必填）
   - `TRAVELPAYOUTS_TOKEN`（免費資料來源，建議至少設這個）
   - `SERPAPI_KEY`（可選；想要更準的即時價再設，會在額度內優先使用）
2. （可選）在同一頁的 **Variables** 分頁可設 `CURRENCY`、`ADULTS` 等，
   不設就用預設值（`TWD` / `1`）。
3. 到 **Actions** 分頁啟用 workflow。第一次可以手動按 **Run workflow** 測試。
4. 之後它每 5 分鐘自動跑一次。你在 Telegram 傳訊息，下一次排程跑時就會回你。

> ⚠️ 重要：GitHub 的排程只會從 **預設分支** 觸發。請確認 `.github/workflows/flight-check.yml`
> 已在你的預設分支上（把這個分支合併到 `main`，或把它設成預設分支）。
>
> ⚠️ 取捨：Actions 是「定時跑」不是「即時掛著」，所以你傳訊息後最多要等約 5 分鐘才會收到回覆
> （GitHub 排程的最短間隔就是 5 分鐘，且高峰時偶爾會再延遲幾分鐘）。對盯機票來說完全夠用。

### B. 在自己電腦／伺服器上跑（即時回覆）

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入你的 token / API key
python main.py
```

這個模式用 `python-telegram-bot` 持續掛著，傳訊息會**即時**回覆。需要一台一直開著的機器。

> 🚀 想免費、穩定、又能秒回（適合分享給朋友）？用 GCP 永久免費的 e2-micro VM 跑模式 B，
> 步驟見 **[deploy/GCP_SETUP.md](deploy/GCP_SETUP.md)**。
> 已經有一台跑 `docker compose` 的機器、想共用？見 **[deploy/DOCKER.md](deploy/DOCKER.md)**。
> 注意：跑模式 B 時請把 GitHub Actions 的排程停用，避免兩邊搶收訊息。

### 需要的金鑰

| 變數 | 必填 | 怎麼拿 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | ✅ | 在 Telegram 找 [@BotFather](https://t.me/BotFather) 建一個 bot |
| `TRAVELPAYOUTS_TOKEN` | 至少一個 | 到 [travelpayouts.com](https://www.travelpayouts.com) 免費註冊取得 token |
| `SERPAPI_KEY` | 至少一個 | 到 [serpapi.com](https://serpapi.com) 註冊取得 API key（免費額度約 100 次/月）|

> 至少要設 `TRAVELPAYOUTS_TOKEN` 或 `SERPAPI_KEY` 其中一個；兩個都設會自動 fallback。
> 其餘可調設定（檢查間隔、幣別、人數、通知門檻）都在 `.env.example` 有註解。

## 怎麼用

啟動後在 Telegram 跟你的 bot 對話：

```
你：從 TPE 到 NRT 7/1 出發 7/10 回程 低於 12000
Bot：✅ 已建立監控 …（並回報目前最低價）

你：/list           ← 看所有監控
你：/check          ← 立刻查一次
你：/del 1          ← 刪掉 #1
```

支援的訊息寫法：

- 航線：`從X到Y`、`X到Y`、`X -> Y`、`X→Y`（X/Y 可填三碼 IATA 或常見城市中文名）
- 轉乘：`經X`、`轉X`、`經由X`、`中轉X`、`via X`
- 日期：`7/1`、`2026-07-01`、`7月1日`；第一個是去程、第二個是回程，寫「單程」則忽略回程
- 預算：`低於12000`、`預算12000`、`<12000`

## 架構

```
main.py                 啟動入口（模式 B：持續掛著、即時回覆）
runner.py               一次性執行（模式 A：GitHub Actions 定時跑）
.github/workflows/
  flight-check.yml      每 5 分鐘自動查價並把狀態 commit 回 repo
src/
  config.py             讀環境變數
  parser.py             訊息 → 監控設定（純邏輯，有測試）
  flight_offer.py       共用的 FlightOffer 型別與例外
  providers/            機票資料來源（可插拔）
    travelpayouts.py    免費、不按次計費（預設）
    serpapi.py          Google Flights，準、即時，免費額度小
    fallback.py         主來源額度用盡時自動退回備援
    __init__.py         build_provider 工廠
  storage.py            SQLite 儲存監控（模式 B 用）
  json_storage.py       JSON 檔儲存（模式 A 用，可 commit 回 repo）
  monitor.py            判價邏輯：是否該通知（純邏輯，有測試）
  messages.py           組 Telegram 訊息文字
  telegram_api.py       輕量 Telegram API（requests，模式 A 用）
  bot.py                Telegram handlers + 定時排程（模式 B 用）
tests/                  parser / monitor / json_storage / providers 單元測試（免網路）
```

## 測試

```bash
pytest
```

## 備註

- **Travelpayouts** 的價格是快取結果（別人搜過的最低價），非每次即時；且只給轉乘次數、
  不給中轉機場，所以指定 `經 X` 時為盡力而為（有轉乘就不排除、直飛則排除）。要精準的 via
  與即時價，設定 `SERPAPI_KEY` 即可在額度內優先使用。
- 「強制經過某機場」是抓回報價後在 `monitor.py` 依轉乘機場過濾，而非由 API 端篩選。
- 原 Amadeus 自助版 API 將於 2026/7/17 停用，本專案已改為上述可插拔來源。
