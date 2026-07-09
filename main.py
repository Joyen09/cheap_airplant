"""啟動入口：python main.py"""
from __future__ import annotations

import logging

from src.bot import FlightBot
from src.config import Config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx 在 INFO 會把含 token 的完整網址印進 log，壓到 WARNING 避免外洩
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = Config.load()
    if not config.telegram_token:
        raise RuntimeError("要跑 Telegram 版請設定 TELEGRAM_BOT_TOKEN；用 Discord 請改跑 main_discord.py")
    FlightBot(config).run()


if __name__ == "__main__":
    main()
