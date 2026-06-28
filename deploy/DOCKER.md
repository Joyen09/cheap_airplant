# 用 Docker 跑（可與其他 bot 共用同一台 VM）

適合你已經有一台跑 `docker compose` 的 VM（例如 grid bot 那台）。
flight-bot 會以一個獨立容器跑，吃資源很少（約 35MB），跟 grid 互不影響。

> ⚠️ 一個 Telegram bot 只能有一個程式在收訊息。搬過來前，請先把**舊的那台
> flight-bot VM** 上的服務停掉：`sudo systemctl disable --now cheap-airplant`
> （或直接刪掉那台 VM），否則兩邊會搶收訊息而衝突。

---

## 方式 A：併入你既有的 compose 專案（推薦，和 grid 同一個）

假設你的專案在 `~/bot`、裡面的 `docker-compose.yml` 有 `grid` 服務：

```bash
cd ~/bot
git clone https://github.com/Joyen09/cheap_airplant.git
cp cheap_airplant/.env.example cheap_airplant/.env
nano cheap_airplant/.env       # 填 TELEGRAM_BOT_TOKEN、TRAVELPAYOUTS_TOKEN（SERPAPI_KEY 可留空）
```

把這段服務貼進 `~/bot/docker-compose.yml` 的 `services:` 底下：

```yaml
  flight-bot:
    build: ./cheap_airplant
    container_name: flight-bot
    env_file: ./cheap_airplant/.env
    volumes:
      - ./cheap_airplant/data:/app/data
    restart: unless-stopped
```

然後只建這個服務、看它的 log（grid 不受影響）：

```bash
docker compose up -d --build flight-bot
docker compose logs -f flight-bot
```

## 方式 B：獨立跑（不想動到既有 compose）

```bash
git clone https://github.com/Joyen09/cheap_airplant.git
cd cheap_airplant
cp .env.example .env && nano .env     # 填金鑰
docker compose up -d --build
docker compose logs -f flight-bot
```

---

## 日常維護

```bash
# 更新到最新版
cd ~/bot/cheap_airplant && git pull
cd ~/bot && docker compose up -d --build flight-bot

# 看狀態 / 日誌
docker compose ps
docker compose logs -f flight-bot

# 停止 / 重啟
docker compose stop flight-bot
docker compose restart flight-bot
```

監控資料存在 `cheap_airplant/data/`（透過 volume 掛載），重建容器不會遺失。
