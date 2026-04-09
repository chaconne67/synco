"""Telegram Bot instance factory.

Does NOT register webhooks. Use management command `setup_telegram_webhook` for that.
"""

from __future__ import annotations

import logging

from django.conf import settings
from telegram import Bot

logger = logging.getLogger(__name__)

_bot_instance: Bot | None = None


def get_bot() -> Bot:
    """Return a shared Bot instance. Raises if token is not configured."""
    global _bot_instance
    if _bot_instance is None:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable before using Telegram features."
            )
        _bot_instance = Bot(token=token)
    return _bot_instance


def reset_bot() -> None:
    """Reset the cached bot instance (for testing)."""
    global _bot_instance
    _bot_instance = None
