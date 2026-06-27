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

## 安裝

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入你的 token / API key
python main.py
```

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
main.py                 啟動入口
src/
  config.py             讀環境變數
  parser.py             訊息 → 監控設定（純邏輯，有測試）
  amadeus_client.py     Amadeus OAuth2 + 查價
  storage.py            SQLite 儲存監控
  monitor.py            判價邏輯：是否該通知（純邏輯，有測試）
  messages.py           組 Telegram 訊息文字
  bot.py                Telegram handlers + 定時排程
tests/                  parser / monitor 單元測試（免網路）
```

## 測試

```bash
pytest
```

## 備註

- 沙盒環境（`test`）的航線與價格有限，是 demo 用；要看真實價格請申請 production 金鑰。
- Amadeus 的 Flight Offers Search 本身不支援「強制經過某機場」，本專案是
  抓回報價後在 `monitor.py` 依轉乘機場過濾。
