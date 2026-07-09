"""Discord 版啟動入口：python main_discord.py"""
from __future__ import annotations

import logging

from src.config import Config
from src.discord_bot import FlightDiscordBot


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.load()
    if not config.discord_token:
        raise RuntimeError(
            "要跑 Discord 版請設定 DISCORD_BOT_TOKEN；用 Telegram 請改跑 main.py"
        )
    FlightDiscordBot(config).run()


if __name__ == "__main__":
    main()
