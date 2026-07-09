# 用 Discord 跑（功能與 Telegram 版一模一樣）

核心邏輯完全共用，只是換成 Discord 對話。跑的是 `main_discord.py`。

## 1. 建立 Discord bot、拿 token

1. 到 <https://discord.com/developers/applications> → **New Application**，取個名字。
2. 左側 **Bot** → **Reset Token / Copy**，複製 token（這就是 `DISCORD_BOT_TOKEN`）。
3. 同一頁把 **MESSAGE CONTENT INTENT** 打開（很重要，否則機器人讀不到你的訊息）。

## 2. 把 bot 加進一個伺服器（才能私訊它）

1. 左側 **OAuth2 → URL Generator**：SCOPES 勾 **bot**；BOT PERMISSIONS 勾
   **Send Messages**、**Attach Files**（傳走勢圖用）、**Read Message History**。
2. 複製產生的邀請網址、在瀏覽器開啟，把 bot 邀進你自己的伺服器（沒有的話先建一個免費伺服器）。

## 3. 設定並啟動

`.env` 填入（Telegram 那行可留空）：

```
DISCORD_BOT_TOKEN=你的-discord-bot-token
TRAVELPAYOUTS_TOKEN=你的-travelpayouts-token
```

### 本機 / VM 直接跑
```bash
python main_discord.py
```

### Docker（和其他 bot 共用時）
在 compose 服務裡把啟動指令指到 discord 版：
```yaml
  flight-bot:
    build: ./cheap_airplant
    image: cheap-airplant
    container_name: flight-bot
    restart: unless-stopped
    env_file: ./cheap_airplant/.env
    command: ["python", "main_discord.py"]   # ← 關鍵：跑 Discord 版
    volumes:
      - ./cheap_airplant/data:/app/data
```
```bash
docker compose up -d --build flight-bot
docker compose logs -f flight-bot
```

## 怎麼用

- **私訊機器人**（DM）：直接打字就行，跟 Telegram 一樣。
  例：`從 TPE 到 NRT 9/26 出發 10/4 回程 去程 09:00 後 低於 25000`
- **按鈕流程**：打 `new` → 按【➕ 建立監控】→ 填表單 → 送出後會**先顯示目前行情**
  （最低/中位數＋建議預算），再用選單挑去程/回程時段、按鈕設轉機點與預算 → ✅ 建立。
- **在伺服器頻道**：訊息前加 `!` 或 **@提及機器人**（避免它回應所有訊息）。
  例：`!list`、`!chart 1`
- 指令：`help`、`new`、`list`、`del <編號>`、`check`、`chart [編號]`（加不加 `/`、`!` 都行）。

> 想私訊 bot：你必須和它在同一個伺服器裡（步驟 2 完成後即可）。
