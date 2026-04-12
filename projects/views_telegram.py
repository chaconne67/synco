"""Telegram webhook and binding views."""

from __future__ import annotations

import json
import logging
import random
import string
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import TelegramBinding, TelegramVerification
from projects.telegram.auth import validate_webhook_secret

logger = logging.getLogger(__name__)

DEDUP_TTL = 300  # 5 minutes


def _safe_send(chat_id: str, text: str) -> None:
    """Send a Telegram message, swallowing exceptions."""
    from projects.services.notification import _send_telegram_message

    try:
        _send_telegram_message(chat_id, text)
    except Exception:
        logger.exception("Failed to send message to %s", chat_id)


def _process_update(data: dict) -> None:
    """Process a Telegram update (callback_query or message)."""
    from projects.telegram.handlers import (
        handle_approval_callback,
        handle_contact_callback,
    )
    from projects.telegram.keyboards import parse_callback_data
    from projects.telegram.auth import verify_telegram_user_access
    from projects.models import Notification, ProjectApproval

    # Handle callback_query (button press)
    callback_query = data.get("callback_query")
    if callback_query:
        # A11: Callback query ID dedup
        cq_id = callback_query.get("id", "")
        if cq_id:
            cq_cache_key = f"tg_cq:{cq_id}"
            if cache.get(cq_cache_key):
                return
            cache.set(cq_cache_key, True, DEDUP_TTL)

        cb_data = callback_query.get("data", "")
        parsed = parse_callback_data(cb_data)
        if not parsed:
            logger.warning("Invalid callback_data: %s", cb_data)
            return

        short_id = parsed["notification_short_id"]
        action = parsed["action"]

        # Find notification by short_id (UUID hex prefix)
        notifications = Notification.objects.filter(id__startswith=short_id)
        if notifications.count() != 1:
            logger.warning("Cannot resolve notification for short_id: %s", short_id)
            return
        notification = notifications.first()

        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
        cb = notification.callback_data
        notif_action = cb.get("action", "")

        try:
            if notif_action == "approval":
                # A8: Look up actual ProjectApproval model first
                approval = ProjectApproval.objects.select_related("project").get(
                    pk=notification.callback_data["approval_id"]
                )
                user, _ = verify_telegram_user_access(chat_id, approval.project)
                handle_approval_callback(
                    notification=notification,
                    action=action,
                    user=user,
                )
            elif notif_action == "contact_record":
                from projects.models import Project

                project = Project.objects.get(pk=cb["project_id"])
                user, _ = verify_telegram_user_access(chat_id, project)
                handle_contact_callback(
                    notification=notification,
                    action=action,
                    user=user,
                )
        except Exception:
            logger.exception(
                "Error handling callback for notification %s", notification.pk
            )
        return

    # Handle text message
    message = data.get("message")
    if message:
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Handle /start command for binding
        if text.startswith("/start "):
            code = text[7:].strip()
            _handle_start_command(chat_id, code)
            return

        # A2: Handle free-text messages via intent parser
        _handle_text_message(chat_id, text)


def _handle_text_message(chat_id: str, text: str) -> None:
    """Handle free-text messages via intent parser (Amendment A2)."""
    try:
        binding = TelegramBinding.objects.get(chat_id=chat_id, is_active=True)
    except TelegramBinding.DoesNotExist:
        _safe_send(
            chat_id, "텔레그램 연동이 필요합니다. 웹 앱에서 연동을 진행해주세요."
        )
        return

    user = binding.user
    from accounts.models import Membership

    try:
        membership = Membership.objects.select_related("organization").get(user=user)
        org = membership.organization
    except Membership.DoesNotExist:
        _safe_send(chat_id, "조직 소속이 없습니다.")
        return

    # A3: Check for awaiting_text_input state
    from projects.models import Notification

    pending = (
        Notification.objects.filter(
            recipient=user,
            callback_data__contains={"awaiting_text_input": True},
        )
        .order_by("-created_at")
        .first()
    )
    if pending:
        _handle_awaiting_text(pending, text, chat_id)
        return

    # Try P14 intent parser (graceful fallback)
    try:
        from projects.services.voice.intent_parser import parse_intent

        result = parse_intent(text, context={"user": user, "organization": org})
        _handle_parsed_intent(chat_id, result, user, org)
    except ImportError:
        _safe_send(chat_id, "텍스트 명령은 아직 준비 중입니다. 웹 앱을 이용해주세요.")
    except Exception:
        logger.exception("Error handling text message")
        _safe_send(chat_id, "요청 처리 중 오류가 발생했습니다.")


def _handle_awaiting_text(notification, text: str, chat_id: str) -> None:
    """Handle text input for awaiting_text_input state (Amendment A3)."""
    from projects.services.approval import send_admin_message
    from projects.models import ProjectApproval

    approval_id = notification.callback_data.get("approval_id")
    if approval_id:
        try:
            approval = ProjectApproval.objects.get(pk=approval_id)
            send_admin_message(approval, notification.recipient, text)
            notification.callback_data["awaiting_text_input"] = False
            notification.save(update_fields=["callback_data"])
            from projects.services.notification import update_telegram_message

            update_telegram_message(notification, f"💬 메시지 전송 완료: {text[:50]}")
        except Exception:
            logger.exception("Error sending admin message")
            _safe_send(chat_id, "메시지 전송에 실패했습니다.")


def _handle_parsed_intent(chat_id: str, result, user, org) -> None:
    """Handle parsed intent from P14 intent parser."""
    # Basic implementation — expand based on P14 intent types
    intent = None
    if isinstance(result, dict):
        intent = result.get("intent")
    else:
        intent = getattr(result, "intent", None)
    if not intent:
        _safe_send(chat_id, "요청을 이해하지 못했습니다. 다시 입력해주세요.")
        return
    _safe_send(chat_id, f"'{intent}' 요청을 처리 중입니다...")


def _handle_start_command(chat_id: str, code: str) -> None:
    """Handle /start <code> command for binding verification (A9: brute force defense)."""
    # A9: Find verification by code, decouple from attempt tracking
    verification = (
        TelegramVerification.objects.filter(
            code=code,
            consumed=False,
            expires_at__gt=timezone.now(),
        )
        .select_related("user")
        .first()
    )

    if not verification:
        _safe_send(chat_id, "인증 코드가 만료되었거나 존재하지 않습니다.")
        return

    # Increment attempts FIRST
    verification.attempts += 1
    verification.save(update_fields=["attempts"])

    if verification.is_blocked:
        _safe_send(chat_id, "인증 시도 횟수를 초과했습니다. 새 코드를 발급해주세요.")
        return

    # Success
    verification.consumed = True
    verification.save(update_fields=["consumed"])

    TelegramBinding.objects.update_or_create(
        user=verification.user,
        defaults={
            "chat_id": chat_id,
            "is_active": True,
            "verified_at": timezone.now(),
        },
    )
    _safe_send(chat_id, "✅ synco 텔레그램 연동이 완료되었습니다!")


@csrf_exempt
@require_POST
def telegram_webhook(request):
    """POST /telegram/webhook/ — Telegram Bot webhook endpoint."""
    if not validate_webhook_secret(request):
        return HttpResponse(status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    # Idempotency: check update_id
    update_id = data.get("update_id")
    if update_id:
        cache_key = f"tg_update:{update_id}"
        if cache.get(cache_key):
            return HttpResponse(status=200)
        cache.set(cache_key, True, DEDUP_TTL)

    try:
        _process_update(data)
    except Exception:
        logger.exception("Error processing Telegram update")

    return HttpResponse(status=200)


@login_required
def telegram_bind(request):
    """GET/POST /telegram/bind/ — Telegram binding settings."""
    template = "accounts/telegram_bind.html"

    if request.method == "POST":
        user = request.user

        # Invalidate previous codes
        TelegramVerification.objects.filter(
            user=user,
            consumed=False,
        ).update(consumed=True)

        # A10: Generate code with collision check
        code = None
        for _ in range(3):
            candidate_code = "".join(random.choices(string.digits, k=6))
            collision = TelegramVerification.objects.filter(
                code=candidate_code,
                consumed=False,
                expires_at__gt=timezone.now(),
            ).exists()
            if not collision:
                code = candidate_code
                break

        if code is None:
            return render(
                request,
                template,
                {"error": "코드 생성에 실패했습니다. 다시 시도해주세요."},
            )

        TelegramVerification.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        try:
            binding = TelegramBinding.objects.get(user=user)
            is_bound = binding.is_active
        except TelegramBinding.DoesNotExist:
            is_bound = False

        return render(
            request,
            template,
            {
                "code": code,
                "is_bound": is_bound,
                "expires_minutes": 5,
            },
        )

    # GET
    try:
        binding = TelegramBinding.objects.get(user=request.user)
        is_bound = binding.is_active
        verified_at = binding.verified_at
    except TelegramBinding.DoesNotExist:
        is_bound = False
        verified_at = None

    return render(
        request,
        template,
        {
            "is_bound": is_bound,
            "verified_at": verified_at,
        },
    )


@login_required
@require_POST
def telegram_unbind(request):
    """POST /telegram/unbind/ — Deactivate Telegram binding."""
    template = "accounts/telegram_bind.html"
    try:
        binding = TelegramBinding.objects.get(user=request.user)
        binding.is_active = False
        binding.save(update_fields=["is_active"])
    except TelegramBinding.DoesNotExist:
        pass

    return render(
        request,
        template,
        {
            "is_bound": False,
            "message": "텔레그램 연동이 해제되었습니다.",
        },
    )


@login_required
def telegram_bind_partial(request):
    """Settings tab partial for telegram binding. Reuses bind logic."""
    template = "accounts/partials/settings_telegram.html"

    if request.method == "POST":
        user = request.user

        # Invalidate previous codes
        TelegramVerification.objects.filter(
            user=user,
            consumed=False,
        ).update(consumed=True)

        code = None
        for _ in range(3):
            candidate_code = "".join(random.choices(string.digits, k=6))
            collision = TelegramVerification.objects.filter(
                code=candidate_code,
                consumed=False,
                expires_at__gt=timezone.now(),
            ).exists()
            if not collision:
                code = candidate_code
                break

        if code is None:
            return render(
                request,
                template,
                {"error": "코드 생성에 실패했습니다. 다시 시도해주세요.", "active_tab": "telegram"},
            )

        TelegramVerification.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        try:
            binding = TelegramBinding.objects.get(user=user)
            is_bound = binding.is_active
        except TelegramBinding.DoesNotExist:
            is_bound = False

        return render(
            request,
            template,
            {"code": code, "is_bound": is_bound, "expires_minutes": 5, "active_tab": "telegram"},
        )

    # GET
    try:
        binding = TelegramBinding.objects.get(user=request.user)
        is_bound = binding.is_active
        verified_at = binding.verified_at
    except TelegramBinding.DoesNotExist:
        is_bound = False
        verified_at = None

    return render(
        request,
        template,
        {"is_bound": is_bound, "verified_at": verified_at, "active_tab": "telegram"},
    )


@login_required
@require_POST
def telegram_test_send(request):
    """POST /telegram/test/ — Send a test message."""
    from projects.services.notification import _send_telegram_message

    template = "accounts/telegram_bind.html"

    try:
        binding = TelegramBinding.objects.get(user=request.user, is_active=True)
    except TelegramBinding.DoesNotExist:
        return render(
            request,
            template,
            {
                "is_bound": False,
                "error": "텔레그램이 연결되어 있지 않습니다.",
            },
        )

    try:
        _send_telegram_message(binding.chat_id, "🤖 synco 테스트 메시지입니다!")
        return render(
            request,
            template,
            {
                "is_bound": True,
                "verified_at": binding.verified_at,
                "message": "테스트 메시지가 전송되었습니다.",
            },
        )
    except Exception:
        return render(
            request,
            template,
            {
                "is_bound": True,
                "verified_at": binding.verified_at,
                "error": "메시지 전송에 실패했습니다.",
            },
        )


@login_required
@require_POST
def telegram_test_partial(request):
    """POST /telegram/test-partial/ — Test message, returns settings tab partial."""
    from projects.services.notification import _send_telegram_message

    template = "accounts/partials/settings_telegram.html"

    try:
        binding = TelegramBinding.objects.get(user=request.user, is_active=True)
    except TelegramBinding.DoesNotExist:
        return render(request, template, {
            "is_bound": False,
            "error": "텔레그램이 연결되어 있지 않습니다.",
            "active_tab": "telegram",
        })

    try:
        _send_telegram_message(binding.chat_id, "🤖 synco 테스트 메시지입니다!")
        return render(request, template, {
            "is_bound": True,
            "verified_at": binding.verified_at,
            "message": "테스트 메시지가 전송되었습니다.",
            "active_tab": "telegram",
        })
    except Exception:
        return render(request, template, {
            "is_bound": True,
            "verified_at": binding.verified_at,
            "error": "메시지 전송에 실패했습니다.",
            "active_tab": "telegram",
        })


@login_required
@require_POST
def telegram_unbind_partial(request):
    """POST /telegram/unbind-partial/ — Unbind, returns settings tab partial."""
    template = "accounts/partials/settings_telegram.html"

    try:
        binding = TelegramBinding.objects.get(user=request.user)
        binding.is_active = False
        binding.save(update_fields=["is_active"])
    except TelegramBinding.DoesNotExist:
        pass

    return render(request, template, {
        "is_bound": False,
        "message": "텔레그램 연동이 해제되었습니다.",
        "active_tab": "telegram",
    })
