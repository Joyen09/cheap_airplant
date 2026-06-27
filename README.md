# ✈️ 便宜機票通知機器人 (cheap_airplant)

透過 Telegram 監控機票價格：你傳一段訊息說「從哪到哪、要不要轉乘、什麼日期、預算多少」，
機器人就會用 [Amadeus](https://developers.amadeus.com) 的報價 API 定時幫你查價，
**便宜了或創新低就主動推播通知**給你。

## 功能

- 📩 **自然語言建立監控**：傳 `從 TPE 到 NRT 經 HKG 7/1 出發 7/10 回程 低於 12000` 即可。
- 🔁 **轉乘點過濾**：指定「經 X」時，只比較有經過該機場的航班。
- ⏰ **定時自動查價**：預設每 60 分鐘掃一次所有監控（可調）。
- 🔔 **兩種通知條件**：價格低於你設的預算，或比歷史最低再便宜一定比例。
- 🗂️ **多監控管理**：`/list`、`/del`、`/check`。

## 兩種跑法

### A. 全程在 GitHub 上跑（推薦，免下載、免伺服器）

靠 **GitHub Actions** 每 30 分鐘自動執行一次：讀你傳的新訊息、查價、便宜就通知，
狀態存回 repo 裡的 `bot_state.json`。你完全不用開電腦。

設定步驟（都在瀏覽器完成）：

1. 這個 repo 的 **Settings → Secrets and variables → Actions → New repository secret**，
   新增三個 secret：
   - `TELEGRAM_BOT_TOKEN`
   - `AMADEUS_CLIENT_ID`
   - `AMADEUS_CLIENT_SECRET`
2. （可選）在同一頁的 **Variables** 分頁可設 `AMADEUS_ENV`、`CURRENCY`、`ADULTS` 等，
   不設就用預設值（`test` / `TWD` / `1`）。
3. 到 **Actions** 分頁啟用 workflow。第一次可以手動按 **Run workflow** 測試。
4. 之後它每 30 分鐘自動跑一次。你在 Telegram 傳訊息，下一次排程跑時就會回你。

> ⚠️ 重要：GitHub 的排程只會從 **預設分支** 觸發。請確認 `.github/workflows/flight-check.yml`
> 已在你的預設分支上（把這個分支合併到 `main`，或把它設成預設分支）。
>
> ⚠️ 取捨：Actions 是「定時跑」不是「即時掛著」，所以你傳訊息後最多要等約 30 分鐘才會收到回覆。
> 對盯機票來說完全夠用。想更頻繁可改 `flight-check.yml` 裡的 `cron`（GitHub 最短約 5 分鐘）。

### B. 在自己電腦／伺服器上跑（即時回覆）

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入你的 token / API key
python main.py
```

這個模式用 `python-telegram-bot` 持續掛著，傳訊息會**即時**回覆。需要一台一直開著的機器。

### 需要的金鑰

| 變數 | 怎麼拿 |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | 在 Telegram 找 [@BotFather](https://t.me/BotFather) 建一個 bot |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | 到 [developers.amadeus.com](https://developers.amadeus.com) 註冊、建立 App |

> `AMADEUS_ENV=test` 是免費沙盒（資料較少、價格非即時）；上線時改成 `production`。
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
  flight-check.yml      每 30 分鐘自動查價並把狀態 commit 回 repo
src/
  config.py             讀環境變數
  parser.py             訊息 → 監控設定（純邏輯，有測試）
  amadeus_client.py     Amadeus OAuth2 + 查價
  storage.py            SQLite 儲存監控（模式 B 用）
  json_storage.py       JSON 檔儲存（模式 A 用，可 commit 回 repo）
  monitor.py            判價邏輯：是否該通知（純邏輯，有測試）
  messages.py           組 Telegram 訊息文字
  telegram_api.py       輕量 Telegram API（requests，模式 A 用）
  bot.py                Telegram handlers + 定時排程（模式 B 用）
tests/                  parser / monitor / json_storage 單元測試（免網路）
```

## 測試

```bash
pytest
```

## 備註

- 沙盒環境（`test`）的航線與價格有限，是 demo 用；要看真實價格請申請 production 金鑰。
- Amadeus 的 Flight Offers Search 本身不支援「強制經過某機場」，本專案是
  抓回報價後在 `monitor.py` 依轉乘機場過濾。
