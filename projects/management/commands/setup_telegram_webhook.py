"""Register Telegram webhook URL with the Bot API."""

from __future__ import annotations

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Register the Telegram Bot webhook URL"

    def handle(self, *args, **options):
        from projects.telegram.bot import get_bot

        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN is not configured")

        site_url = settings.SITE_URL
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        webhook_url = f"{site_url}/telegram/webhook/"

        bot = get_bot()

        async def _setup():
            result = await bot.set_webhook(
                url=webhook_url,
                secret_token=secret if secret else None,
            )
            return result

        success = asyncio.run(_setup())

        if success:
            self.stdout.write(
                self.style.SUCCESS(f"Webhook registered: {webhook_url}")
            )
        else:
            raise CommandError("Failed to register webhook")
