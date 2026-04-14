"""Telegram callback and message handlers.

All business logic delegates to existing service functions.
Handlers are thin wrappers that translate Telegram actions to service calls.
"""

from __future__ import annotations

import logging


from accounts.models import User
from projects.models import Notification, ProjectApproval
from projects.services.approval import (
    InvalidApprovalTransition,
    approve_project,
    merge_project,
    reject_project,
)

logger = logging.getLogger(__name__)


def _update_notification_message(notification: Notification, text: str) -> None:
    """Update the Telegram message for a notification (fire-and-forget)."""
    from projects.services.notification import update_telegram_message

    try:
        update_telegram_message(notification, text)
    except Exception:
        logger.exception("Failed to update telegram message for %s", notification.pk)


def _send_next_step(
    *,
    recipient: User,
    callback_data: dict,
    text: str,
    reply_markup=None,
) -> Notification:
    """Create a new Notification for the next step and send it."""
    from projects.services.notification import send_notification

    notif = Notification.objects.create(
        recipient=recipient,
        type=Notification.Type.AUTO_GENERATED,
        title="알림",
        body=text,
        callback_data=callback_data,
    )
    send_notification(notif, text=text, reply_markup=reply_markup)
    return notif


def _update_notification_with_keyboard(
    notification: Notification, text: str, reply_markup
) -> None:
    """Update a sent notification's message with a keyboard (A4 two-phase send).

    Used when we need to create the notification first to get its pk,
    then build a keyboard referencing that pk.
    """
    from projects.services.notification import update_telegram_message

    try:
        update_telegram_message(notification, text, reply_markup=reply_markup)
    except Exception:
        logger.exception(
            "Failed to update notification %s with keyboard", notification.pk
        )


def handle_approval_callback(
    *,
    notification: Notification,
    action: str,
    user: User,
) -> dict:
    """Handle approval-related callback actions.

    Actions: approve, reject, join, message
    Delegates to projects/services/approval.py functions.

    AMENDMENT A6: Save project title before calling service (service may delete project).
    """
    approval_id = notification.callback_data.get("approval_id")
    if not approval_id:
        return {"ok": False, "error": "승인 데이터가 없습니다."}

    try:
        approval = ProjectApproval.objects.select_related("project").get(pk=approval_id)
    except ProjectApproval.DoesNotExist:
        return {"ok": False, "error": "승인 요청을 찾을 수 없습니다."}

    try:
        # A6: Save title before service call (project may be deleted)
        project_title = approval.project.title

        if action == "approve":
            approve_project(approval, user)
            _update_notification_message(
                notification, f"✅ 승인 완료 — {project_title}"
            )
            return {"ok": True, "result": "approved"}

        elif action == "reject":
            reject_project(approval, user)
            _update_notification_message(
                notification, f"❌ 반려 완료 — {project_title}"
            )
            return {"ok": True, "result": "rejected"}

        elif action == "join":
            merge_project(approval, user)
            _update_notification_message(
                notification, f"🔗 합류 완료 — {project_title}"
            )
            return {"ok": True, "result": "joined"}

        elif action == "message":
            # A3: Message action with awaiting_text_input state
            notification.callback_data["awaiting_text_input"] = True
            notification.save(update_fields=["callback_data"])
            return {
                "ok": True,
                "result": "awaiting_message",
                "prompt": "메시지를 입력해주세요.",
            }

        else:
            return {"ok": False, "error": f"알 수 없는 액션: {action}"}

    except InvalidApprovalTransition as e:
        return {"ok": False, "error": str(e)}
