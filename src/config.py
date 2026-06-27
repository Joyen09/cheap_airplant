"""集中讀取環境變數設定。"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(
            f"缺少必要的環境變數 {key}，請參考 .env.example 設定後再啟動。"
        )
    return value or ""


@dataclass(frozen=True)
class Config:
    telegram_token: str
    # 機票資料來源：至少要設定其中一個
    travelpayouts_token: str
    serpapi_key: str
    check_interval_minutes: int
    currency: str
    adults: int
    new_low_notify_ratio: float
    db_path: str

    @classmethod
    def load(cls) -> "Config":
        config = cls(
            telegram_token=_get("TELEGRAM_BOT_TOKEN", required=True),
            travelpayouts_token=_get("TRAVELPAYOUTS_TOKEN"),
            serpapi_key=_get("SERPAPI_KEY"),
            check_interval_minutes=int(_get("CHECK_INTERVAL_MINUTES", "60")),
            currency=_get("CURRENCY", "TWD"),
            adults=int(_get("ADULTS", "1")),
            new_low_notify_ratio=float(_get("NEW_LOW_NOTIFY_RATIO", "0.05")),
            db_path=_get("DB_PATH", "data/watches.db"),
        )
        if not config.travelpayouts_token and not config.serpapi_key:
            raise RuntimeError(
                "請至少設定一個機票資料來源：TRAVELPAYOUTS_TOKEN 或 SERPAPI_KEY"
                "（見 .env.example）。"
            )
        return config
