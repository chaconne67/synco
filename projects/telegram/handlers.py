"""Telegram callback and message handlers.

All business logic delegates to existing service functions.
Handlers are thin wrappers that translate Telegram actions to service calls.
"""

from __future__ import annotations

import logging


from accounts.models import User
from projects.models import Contact, Notification, ProjectApproval
from projects.services.approval import (
    InvalidApprovalTransition,
    approve_project,
    merge_project,
    reject_project,
)
from projects.services.contact import create_contact

logger = logging.getLogger(__name__)

# Map callback action suffixes to Contact.Channel values
CHANNEL_MAP = {
    "ch_phone": Contact.Channel.PHONE,
    "ch_kakao": Contact.Channel.KAKAO,
    "ch_email": Contact.Channel.EMAIL,
}

# Map callback action suffixes to Contact.Result values
RESULT_MAP = {
    "rs_interest": Contact.Result.INTERESTED,
    "rs_noresp": Contact.Result.NO_RESPONSE,
    "rs_hold": Contact.Result.ON_HOLD,
    "rs_reject": Contact.Result.REJECTED,
}


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
        title="컨택 기록",
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


def handle_contact_callback(
    *,
    notification: Notification,
    action: str,
    user: User,
) -> dict:
    """Handle multi-step contact recording callback.

    Step 1: channel selection (ch_phone, ch_kakao, ch_email)
    Step 2: result selection (rs_interest, rs_noresp, rs_hold, rs_reject)
    Step 3: save (save) — creates Contact via create_contact service (A5)

    AMENDMENT A4: New notification's short_id is used for keyboard (not parent's).
    AMENDMENT A5: Uses create_contact() service function instead of direct ORM.
    """
    cb = notification.callback_data
    step = cb.get("step", 1)
    project_id = cb.get("project_id")
    candidate_id = cb.get("candidate_id")

    from projects.models import Project
    from candidates.models import Candidate
    from projects.telegram.keyboards import (
        build_contact_result_keyboard,
        build_contact_save_keyboard,
    )
    from projects.telegram.formatters import format_contact_step

    try:
        project = Project.objects.get(pk=project_id)
        candidate = Candidate.objects.get(pk=candidate_id)
    except (Project.DoesNotExist, Candidate.DoesNotExist):
        return {"ok": False, "error": "프로젝트 또는 후보자를 찾을 수 없습니다."}

    if step == 1 and action in CHANNEL_MAP:
        # Channel selected → move to step 2 (result selection)
        channel = CHANNEL_MAP[action]
        next_cb = {
            **cb,
            "step": 2,
            "channel": channel,
            "parent_notification_id": str(notification.pk),
        }
        text = format_contact_step(
            candidate_name=candidate.name,
            step="result",
            channel=channel,
        )
        # A4: Create new notification FIRST, then build keyboard with its pk
        next_notif = _send_next_step(
            recipient=user,
            callback_data=next_cb,
            text=text,
        )
        new_short_id = str(next_notif.pk).replace("-", "")[:8]
        _update_notification_with_keyboard(
            next_notif, text, build_contact_result_keyboard(new_short_id)
        )
        return {"ok": True, "next_step": 2}

    elif step == 2 and action in RESULT_MAP:
        # Result selected → move to step 3 (confirm/save)
        result_val = RESULT_MAP[action]
        channel = cb.get("channel", "")
        next_cb = {
            **cb,
            "step": 3,
            "result": result_val,
            "parent_notification_id": str(notification.pk),
        }
        text = format_contact_step(
            candidate_name=candidate.name,
            step="confirm",
            channel=channel,
            result=result_val,
        )
        # A4: Create new notification FIRST, then build keyboard with its pk
        next_notif = _send_next_step(
            recipient=user,
            callback_data=next_cb,
            text=text,
        )
        new_short_id = str(next_notif.pk).replace("-", "")[:8]
        _update_notification_with_keyboard(
            next_notif, text, build_contact_save_keyboard(new_short_id)
        )
        return {"ok": True, "next_step": 3}

    elif step == 3 and action == "save":
        # Final save — A5: delegate to create_contact service
        channel = cb.get("channel", "")
        result_val = cb.get("result", "")

        result = create_contact(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=channel,
            result=result_val,
        )

        if not result["ok"]:
            return {"ok": False, "error": result["error"]}

        _update_notification_message(
            notification,
            f"✅ 컨택 기록 저장 완료\n{candidate.name} | {channel} | {result_val}",
        )
        return {"ok": True, "contact_id": str(result["contact"].pk)}

    return {"ok": False, "error": "잘못된 단계입니다."}
