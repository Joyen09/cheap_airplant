# 在 GCP 永久免費 VM 上跑機器人（模式 B：秒回、穩定）

用 GCP 的 **Always Free e2-micro** 小主機，把 bot 以「一直開著」的方式跑起來。
傳訊息會**即時回覆**，查價也穩定，不再靠 GitHub 排程。適合分享給朋友。

> 💡 模式 B 用 `python main.py`（python-telegram-bot 持續輪詢），所以回覆是即時的；
> `.env` 裡的 `CHECK_INTERVAL_MINUTES` 只控制「背景多久重查一次價格」，不影響回覆速度。

---

## 0. 重要：不要同時開兩個

Telegram 同一個 bot **只能有一個程式在收訊息**。所以在 VM 上跑之前，
請先到 GitHub **Actions → 機票查價 → 右上「⋯」→ Disable workflow** 把排程關掉，
否則兩邊搶著收訊息會互相衝突（429/409）。

---

## 1. 建一台免費 VM

GCP Console → **Compute Engine → VM instances → Create instance**，設定：

- **Region**：`us-central1`（或 `us-west1` / `us-east1`，只有這三區免費）
- **Machine type**：`e2-micro`（一定要這個，選別的就會收費）
- **Boot disk**：Debian 12，大小 ≤ 30GB、類型 Standard persistent disk
- 其他預設即可（不需要開任何對外連接埠，bot 只對外連線）

建立後按該 VM 的 **SSH** 按鈕，開瀏覽器終端機。

## 2. 安裝環境並取得程式

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/Joyen09/cheap_airplant.git
cd cheap_airplant
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. 填入金鑰

```bash
cp .env.example .env
nano .env      # 填 TELEGRAM_BOT_TOKEN、TRAVELPAYOUTS_TOKEN（SERPAPI_KEY 可留空）
```

存檔離開（Ctrl+O、Enter、Ctrl+X）。

## 4. 設成開機自動啟動的服務

```bash
# 把範本裡的 __USER__ 換成你的帳號，安裝成 systemd 服務
sudo sed "s/__USER__/$(whoami)/g" deploy/cheap-airplant.service \
  | sudo tee /etc/systemd/system/cheap-airplant.service
sudo systemctl daemon-reload
sudo systemctl enable --now cheap-airplant
```

## 5. 確認在跑

```bash
systemctl status cheap-airplant        # 顯示 active (running) 就成功
journalctl -u cheap-airplant -f        # 看即時日誌（Ctrl+C 離開）
```

到 Telegram 傳一句航線給 bot，這次會**馬上**回你 ✅

---

## 常用維護指令

```bash
# 之後程式有更新
cd ~/cheap_airplant && git pull && sudo systemctl restart cheap-airplant

# 改設定（.env）後重啟
sudo systemctl restart cheap-airplant

# 看狀態 / 日誌
systemctl status cheap-airplant
journalctl -u cheap-airplant -n 100 --no-pager
```

## 保持免費的注意事項

- 機器務必是 **e2-micro**、區域在 us-central1/us-west1/us-east1。
- 對外流量每月免費 1GB；這個 bot 的流量很小（每次查價只有幾 KB），正常用不會超過。
- 帳單帳號可設「預算提醒」，超過 $0 就寄信通知你，雙重保險。
