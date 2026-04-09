"""Message text formatters for Telegram bot.

All output uses plain text to avoid escaping complexity.
"""

from __future__ import annotations


def format_approval_request(
    *,
    requester_name: str,
    project_title: str,
    conflict_info: str,
    message: str = "",
) -> str:
    """Format approval request notification message."""
    lines = [
        "🤖 [synco] 프로젝트 등록 승인 요청",
        "",
        f"  {requester_name} → {project_title}",
        f"  충돌: {conflict_info}",
    ]
    if message:
        lines.append(f'  메시지: "{message}"')
    return "\n".join(lines)


def format_contact_step(
    *,
    candidate_name: str,
    step: str,
    channel: str = "",
    result: str = "",
) -> str:
    """Format contact recording step message."""
    if step == "channel":
        return f"🤖 {candidate_name} 컨택 결과를 기록합니다.\n\n  연락 방법은?"
    elif step == "result":
        return f"🤖 {candidate_name} 컨택 기록 중\n  채널: {channel}\n\n  결과는?"
    elif step == "confirm":
        return (
            f"🤖 컨택 기록 저장:\n"
            f"  {candidate_name} | {channel} | {result}\n"
            f"  메모를 입력해주세요. (건너뛰려면 아래 버튼)"
        )
    return f"🤖 {candidate_name} 컨택 기록"


def format_reminder(*, reminder_type: str, details: str) -> str:
    """Format reminder notification message."""
    type_labels = {
        "recontact": "📞 재컨택 예정",
        "lock_expiry": "🔓 잠금 만료 임박",
        "submission_review": "📋 서류 검토 대기",
        "interview_tomorrow": "📅 내일 면접",
    }
    label = type_labels.get(reminder_type, "🔔 리마인더")
    return f"{label}\n\n{details}"


def format_todo_list(actions: list[dict]) -> str:
    """Format today's action list."""
    if not actions:
        return "🤖 오늘의 할 일이 없습니다."

    lines = ["🤖 오늘의 할 일:"]
    for i, action in enumerate(actions, 1):
        project = action.get("project_title", "")
        text = action.get("text", "")
        lines.append(f"  {i}. [{project}] {text}")
    return "\n".join(lines)


def format_status_summary(
    *,
    project_title: str,
    status: str,
    contacts_count: int,
    submissions_count: int,
    interviews_count: int,
) -> str:
    """Format project status summary."""
    return (
        f"🤖 {project_title} 현황\n\n"
        f"  상태: {status}\n"
        f"  컨택: {contacts_count}건\n"
        f"  추천: {submissions_count}건\n"
        f"  면접: {interviews_count}건"
    )
