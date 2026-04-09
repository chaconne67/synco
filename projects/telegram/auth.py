"""Telegram webhook authentication and user access verification."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied

from accounts.models import Membership, Organization, TelegramBinding, User

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


def verify_telegram_user_access(chat_id: str, obj) -> tuple[User, Organization]:
    """Verify that the Telegram chat_id maps to a user with access to obj.

    Args:
        chat_id: Telegram chat ID from the update
        obj: Django model instance with an `organization` attribute

    Returns:
        (user, organization) tuple

    Raises:
        PermissionDenied: If binding not found, inactive, or org mismatch
    """
    try:
        binding = TelegramBinding.objects.select_related("user").get(
            chat_id=chat_id, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        raise PermissionDenied("텔레그램 바인딩을 찾을 수 없습니다.")

    user = binding.user

    try:
        membership = Membership.objects.select_related("organization").get(user=user)
    except Membership.DoesNotExist:
        raise PermissionDenied("조직 소속이 없습니다.")

    user_org = membership.organization

    # Check that the object belongs to the user's organization
    obj_org = getattr(obj, "organization", None)
    if obj_org is not None and obj_org != user_org:
        raise PermissionDenied("이 작업에 대한 권한이 없습니다.")

    return user, user_org
