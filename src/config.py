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
    telegram_token: str   # 用 Telegram 才需要
    discord_token: str    # 用 Discord 才需要
    # 機票資料來源：至少要設定其中一個
    travelpayouts_token: str
    serpapi_key: str
    check_interval_minutes: int
    currency: str
    adults: int
    good_deal_ratio: float        # 低於常態價多少比例算「好價」(0.15 = 15%)
    baseline_min_samples: int     # 累積幾筆觀測後才啟用「常態價」判斷
    digest_hour: int              # 每天幾點(台北時間)送摘要
    db_path: str

    @classmethod
    def load(cls) -> "Config":
        config = cls(
            telegram_token=_get("TELEGRAM_BOT_TOKEN"),
            discord_token=_get("DISCORD_BOT_TOKEN"),
            travelpayouts_token=_get("TRAVELPAYOUTS_TOKEN"),
            serpapi_key=_get("SERPAPI_KEY"),
            check_interval_minutes=int(_get("CHECK_INTERVAL_MINUTES", "60")),
            currency=_get("CURRENCY", "TWD"),
            adults=int(_get("ADULTS", "1")),
            good_deal_ratio=float(_get("GOOD_DEAL_RATIO", "0.15")),
            baseline_min_samples=int(_get("BASELINE_MIN_SAMPLES", "10")),
            digest_hour=int(_get("DIGEST_HOUR", "9")),
            db_path=_get("DB_PATH", "data/watches.db"),
        )
        if not config.travelpayouts_token and not config.serpapi_key:
            raise RuntimeError(
                "請至少設定一個機票資料來源：TRAVELPAYOUTS_TOKEN 或 SERPAPI_KEY"
                "（見 .env.example）。"
            )
        return config
