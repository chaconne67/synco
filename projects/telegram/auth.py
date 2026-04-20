"""Telegram webhook authentication and user access verification."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied

from accounts.models import TelegramBinding, User

logger = logging.getLogger(__name__)


def validate_webhook_secret(request) -> bool:
    """Validate the X-Telegram-Bot-Api-Secret-Token header.

    Returns False if the configured secret is empty (misconfigured).
    """
    configured_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not configured_secret:
        logger.warning("TELEGRAM_WEBHOOK_SECRET is not configured")
        return False

    header = request.META.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
    return header == configured_secret


def verify_telegram_user_access(chat_id: str, obj=None) -> User:
    """Verify that the Telegram chat_id maps to an active bound user.

    Args:
        chat_id: Telegram chat ID from the update
        obj: Deprecated — ignored (single-tenant, no org access check needed)

    Returns:
        user

    Raises:
        PermissionDenied: If binding not found or inactive
    """
    try:
        binding = TelegramBinding.objects.select_related("user").get(
            chat_id=chat_id, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        raise PermissionDenied("텔레그램 바인딩을 찾을 수 없습니다.")

    return binding.user
