# ✈️ 便宜機票通知機器人 (cheap_airplant)

透過 **Telegram 或 Discord** 監控機票價格：你用一句話或按鈕告訴它「從哪到哪、要不要
轉乘、什麼日期、幾點的班機、預算多少」，機器人就會定時幫你查價，**便宜了 / 創新低 /
比常態便宜就主動推播通知**給你，還附上「一開就套好所有條件」的 Google Flights 訂票連結。

兩個平台功能一致（共用同一套核心邏輯）：

| 平台 | 啟動 | 設定 |
| --- | --- | --- |
| Telegram | `python main.py`（模式 B）或 `runner.py`（模式 A，GitHub Actions） | @BotFather 拿 token |
| Discord | `python main_discord.py` | 見 **[deploy/DISCORD.md](deploy/DISCORD.md)** |

**機票資料來源**可插拔，依序自動 fallback：
**Google Flights（[fast-flights](https://pypi.org/project/fast-flights/)，免費、即時、免金鑰、原生 TWD）
→ SerpApi（可選）→ Travelpayouts（可選）**。主力免任何 API key，設不設備援都能跑。
（原本的 Amadeus 自助版 API 已於 2026/7 停用。）

## 功能

- 📩 **自然語言建立監控**：傳 `從 TPE 到 NRT 經 HKG 7/1 出發 7/10 回程 低於 12000`。
- 🖱️ **按鈕式精靈（Discord）**：打 `new` → 填表單 → **先顯示目前行情**（最低價/中位數）
  與建議預算 → 用按鈕調時間/轉機/預算 → ✅ 建立。
- 🔁 **多轉乘點過濾**：可指定「經 X 轉 Y」多個轉乘機場（Google/SerpApi 精準；Travelpayouts
  因不提供中轉機場，退為盡力而為）。
- 🕒 **去/回程時間限制**：例如「去程 09:00 後、回程 18:00 前」，Discord 用方向鈕切換前/後。
- 🔔 **三種通知條件**：① 低於你設的預算；② 破歷史新低；③ 明顯低於這條航線「常態價」的好價 🔥。
- 🤫 **不重複轟炸**：同一個條件只有在「比上次通知更便宜」時才會再通知。
- 📈 **價格走勢圖**：`/chart` 回傳含最低點、預算線、常態價線的走勢圖（台灣時間）。
- 📋 **每日摘要**：每天固定回報一次各監控目前最低價，沒觸發也不讓你空等。
- 🔗 **一鍵訂票連結**：通知附 Google Flights 連結，航線/日期/幣別/**時間/轉機條件**全帶入。
- 🔢 **每人獨立編號**：每位使用者從自己的 #1 開始，多人共用同一個 bot 也不會亂。
- 🗂️ **管理指令**：`/list`、`/del`、`/check`、`/chart`。

## 指令

| 指令 | 作用 |
| --- | --- |
| 直接打航線 | 建立監控，例：`從 TPE 到 NRT 經 HKG 7/1 出發 7/10 回程 去程 09:00 後 低於 12000` |
| `new` | （Discord）用按鈕精靈一步步建立，先顯示行情 |
| `/list` | 看自己所有監控 |
| `/del <編號>` | 刪除某個監控 |
| `/check` | 立刻查一次目前價格 |
| `/chart [編號]` | 看價格走勢圖 |
| `/help` | 顯示說明 |

自然語言支援的寫法：

- **航線**：`從X到Y`、`X到Y`、`X -> Y`、`X→Y`（X/Y 可填三碼 IATA 或常見城市中文名）
- **轉乘**：`經X`、`轉X`、`中轉X`、`via X`（可多個）
- **日期**：`7/1`、`2026-07-01`、`7月1日`；第一個去程、第二個回程，寫「單程」則忽略回程
- **時間**：`去程 09:00 後`、`回程 18:00 前`（前/後皆可，支援分鐘）
- **預算**：`低於12000`、`預算12000`、`<12000`

## 三種跑法

| 模式 | 適合 | 回覆速度 | 費用 | 說明 |
| --- | --- | --- | --- | --- |
| **A. GitHub Actions** | 免下載、免伺服器、只用 Telegram | 每 5 分鐘 | 公開 repo 免費 | 見下方 |
| **B. 常駐主機（GCP 免費 VM）** | 想秒回、分享給朋友 | 即時 | GCP e2-micro 永久免費 | **[deploy/GCP_SETUP.md](deploy/GCP_SETUP.md)** |
| **Docker（與其他 bot 共用一台）** | 已有跑 compose 的機器 | 即時 | 依主機 | **[deploy/DOCKER.md](deploy/DOCKER.md)** |

> ⚠️ 同一個 bot 同時只能有一個程式在收訊息。跑模式 B/Docker 時，請把 GitHub Actions 排程停用。

### 模式 A：GitHub Actions（免下載）

`runner.py` 由 `.github/workflows/flight-check.yml` 每 5 分鐘執行：讀新訊息、查價、通知。
狀態檔（`bot_state.json`）保存在 **GitHub Actions cache**、不會 commit 進 repo——裡面有
使用者的 chat id 與旅行計畫（誰、哪天出發、哪天回來），放進版控等於公告行程。
設定（都在瀏覽器）：

1. **Settings → Secrets and variables → Actions → New repository secret** 新增：
   - `TELEGRAM_BOT_TOKEN`（必填）
   - `TRAVELPAYOUTS_TOKEN` / `SERPAPI_KEY`（可選備援；Google Flights 免金鑰，不設也能跑）
2. （可選）**Variables** 分頁可設 `CURRENCY`、`ADULTS`、`GOOD_DEAL_RATIO`、`DIGEST_HOUR`、
   `TRAVELPAYOUTS_MARKER`（分潤連結）等。
3. **Actions** 分頁啟用 workflow，可手動 **Run workflow** 測試。

> - GitHub 排程只從**預設分支**觸發，且非即時（傳訊息後最多等約 5~15 分鐘）。
> - Actions cache **超過 7 天沒被使用會被 GitHub 清掉**（排程正常跑就不會）；
>   若 workflow 停用超過 7 天才重開，狀態會歸零、監控要重新傳訊息建立。
> - GitHub 會在 repo **60 天沒有任何 commit** 時自動停用排程並寄信通知你，
>   到 Actions 頁面按 Enable 即可恢復。

### 模式 B：本機 / 伺服器（即時回覆）

```bash
pip install -r requirements.txt
cp .env.example .env      # 填 token
python main.py            # Telegram
# 或 python main_discord.py   # Discord
```

## 需要的金鑰

| 變數 | 必填 | 怎麼拿 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram 才要 | [@BotFather](https://t.me/BotFather) |
| `DISCORD_BOT_TOKEN` | Discord 才要 | [discord.com/developers](https://discord.com/developers/applications)（記得開 Message Content Intent）|
| `TRAVELPAYOUTS_TOKEN` | 可選 | [travelpayouts.com](https://www.travelpayouts.com)（免費、不按次計費）|
| `SERPAPI_KEY` | 可選 | [serpapi.com](https://serpapi.com)（免費約 100 次/月）|
| `TRAVELPAYOUTS_MARKER` | 可選 | Travelpayouts 後台的 marker（affiliate ID）。設定後通知會多附一條帶分潤的 Aviasales 訂票連結——**使用者票價完全不變**，Travelpayouts 付分潤給你，通知文字已註明含分潤 |

> 平台 token（Telegram 或 Discord）擇一必填。資料來源全部可選——主力 Google Flights 免金鑰。
> 其餘可調設定（檢查間隔、幣別、人數、好價門檻、摘要時間）都在 `.env.example` 有註解。

## 架構

```
main.py                 Telegram 模式 B（持續掛著、即時回覆）
main_discord.py         Discord 模式 B
runner.py               一次性執行（模式 A：GitHub Actions 定時跑）
.github/workflows/
  flight-check.yml      每 5 分鐘查價並把狀態 commit 回 repo
deploy/                 GCP / Docker / Discord 部署指南 + systemd 服務檔
src/
  config.py             讀環境變數
  parser.py             自然語言訊息 → 監控設定（航線/多轉乘/日期/時間/預算）
  flight_offer.py       共用的 FlightOffer 型別與例外
  providers/            機票資料來源（可插拔、鏈式 fallback）
    google_flights.py   fast-flights，免費即時免金鑰（主力）
    serpapi.py          Google Flights 官方代理（可選）
    travelpayouts.py    Aviasales 快取價（可選）
    fallback.py         上一個失敗自動退到下一個
  monitor.py            判價：多轉乘/時間過濾 + 三種通知條件（純邏輯，有測試）
  storage.py            SQLite 儲存 + 每人編號（模式 B）
  json_storage.py       JSON 檔儲存（模式 A，可 commit 回 repo）
  chart.py              matplotlib 價格走勢圖（台灣時間）
  gflink.py             把時間/轉機條件編進 Google Flights tfs 連結
  messages.py           組通知/摘要/清單文字
  wizard_logic.py       Discord 精靈的純邏輯（驗證/時段/行情/建議，有測試）
  discord_wizard.py     Discord 按鈕/表單 UI
  telegram_api.py       輕量 Telegram API（requests，模式 A）
  bot.py                Telegram handlers + 定時排程（模式 B）
  discord_bot.py        Discord handlers + 定時排程（模式 B）
tests/                  parser / monitor / providers / storage / chart /
                        gflink / wizard 單元測試（免網路，共 61 個）
```

## 測試

```bash
pytest
```

## 備註

- **通知價一律是過濾後的價**（符合你的轉乘/時間條件），可信；連結點進 Google Flights 後
  想再微調時間，用它網頁上的拉桿即可（Discord 沒有原生滑桿元件）。
- **Google Flights（fast-flights）** 是非官方管道（解析 Google 頁面），若 Google 改版可能
  暫時失效——屆時會自動退到你設的 SerpApi / Travelpayouts 備援，bot 不會中斷。
- **Travelpayouts** 是快取價（非即時）、且不提供中轉機場，故 via 過濾為盡力而為。
- 「常態價」是用該監控**最近 14 天**實際觀測價的平均當基準（滾動視窗——機票越接近出發日
  通常越貴，太舊的低價不該一直拉低基準），累積約 10 筆觀測後才啟用「好價」判斷。
- 設了 `TRAVELPAYOUTS_MARKER` 時，通知會多附一條帶分潤的 Aviasales 訂票連結，
  並在文字中註明「此連結含開發者分潤，票價不變」——對使用者誠實揭露。
