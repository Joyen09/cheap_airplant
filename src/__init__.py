"""便宜機票通知 — 透過 Telegram 監控機票報價並主動推播。

機票資料來源可插拔（見 src/providers）：預設用免費的 Travelpayouts，
若同時設定 SerpApi 則平常走 SerpApi、額度用盡自動退回 Travelpayouts。
"""
