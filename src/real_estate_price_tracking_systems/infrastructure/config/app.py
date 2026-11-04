"""Process-wide settings: logging and alert delivery."""

from typing import Literal

from pydantic import SecretStr

from real_estate_price_tracking_systems.infrastructure.config.base import BaseSubSettings


class AppSettings(BaseSubSettings):
    CRAWLER_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Telegram alerts. Empty means alerts are not delivered. The token is a secret: it grants
    # full control of the bot.
    TELEGRAM_BOT_TOKEN: SecretStr = SecretStr("")
    TELEGRAM_CHAT_ID: str = ""
