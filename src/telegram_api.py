"""輕量 Telegram Bot API 用戶端（只用 requests，給 GitHub Actions 一次性執行用）。

不依賴 python-telegram-bot，所以在 CI 上跑得又快又輕。
"""
from __future__ import annotations

import requests

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramAPI:
    def __init__(self, token: str):
        self._token = token
        self._session = requests.Session()

    def _call(self, method: str, **params) -> dict:
        resp = self._session.post(
            _API.format(token=self._token, method=method),
            json=params,
            timeout=30,
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} 失敗：{data}")
        return data["result"]

    def get_updates(self, offset: int | None = None) -> list[dict]:
        """抓自上次處理之後的新訊息（不長輪詢，CI 一次性執行用）。"""
        params: dict = {"timeout": 0, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)

    def send_message(self, chat_id: int, text: str, html: bool = True) -> None:
        params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if html:
            params["parse_mode"] = "HTML"
        self._call("sendMessage", **params)
