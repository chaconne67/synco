"""Notification creation, Telegram delivery, and message update service."""

from __future__ import annotations

import asyncio
import logging

from django.conf import settings

from accounts.models import TelegramBinding
from projects.models import Notification

logger = logging.getLogger(__name__)


def _send_telegram_message(
    chat_id: str,
    text: str,
    reply_markup=None,
) -> str:
    """Send a message via Telegram Bot API. Returns message_id as string.

    This is the single point of Telegram API contact for sending.
    Uses synchronous wrapper around async python-telegram-bot.
    """
    from projects.telegram.bot import get_bot

    bot = get_bot()

    async def _send():
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return str(msg.message_id)

    return asyncio.run(_send())


def _edit_telegram_message(
    chat_id: str,
    message_id: str,
    text: str,
    reply_markup=None,
) -> bool:
    """Edit an existing Telegram message. Returns True on success."""
    from projects.telegram.bot import get_bot

    bot = get_bot()

    async def _edit():
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=int(message_id),
            text=text,
            reply_markup=reply_markup,
        )
        return True

    return asyncio.run(_edit())


def send_notification(
    notification: Notification,
    text: str | None = None,
    reply_markup=None,
) -> bool:
    """Send a Notification via Telegram.

    1. Look up recipient's TelegramBinding
    2. If no binding or inactive → return False
    3. Send message → record message_id + chat_id snapshot
    4. On API failure → log + return False (no exception propagation)
    """
    try:
        binding = TelegramBinding.objects.get(
            user=notification.recipient, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        return False

    message_text = text or f"{notification.title}\n\n{notification.body}"

    try:
        message_id = _send_telegram_message(
            chat_id=binding.chat_id,
            text=message_text,
            reply_markup=reply_markup,
        )
        notification.telegram_message_id = message_id
        notification.telegram_chat_id = binding.chat_id
        notification.status = Notification.Status.SENT
        notification.save(
            update_fields=["telegram_message_id", "telegram_chat_id", "status"]
        )
        return True
    except Exception:
        logger.exception(
            "Failed to send Telegram notification %s", notification.pk
        )
        return False


def send_bulk_notifications(notifications: list[Notification]) -> int:
    """Send multiple notifications. Returns count of successful sends."""
    success_count = 0
    for notification in notifications:
        if send_notification(notification):
            success_count += 1
    return success_count


def update_telegram_message(
    notification: Notification,
    new_text: str,
    reply_markup=None,
) -> bool:
    """Update an existing Telegram message.

    1. Check telegram_message_id exists
    2. Compare telegram_chat_id with current binding's chat_id
    3. If mismatch (rebind occurred) → skip, return False
    4. Edit message text
    """
    if not notification.telegram_message_id:
        return False

    if not notification.telegram_chat_id:
        return False

    try:
        binding = TelegramBinding.objects.get(
            user=notification.recipient, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        return False

    # Rebind check: if chat_id changed, don't try to edit old message
    if binding.chat_id != notification.telegram_chat_id:
        return False

    try:
        _edit_telegram_message(
            chat_id=notification.telegram_chat_id,
            message_id=notification.telegram_message_id,
            text=new_text,
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to update Telegram message for notification %s",
            notification.pk,
        )
        return False
