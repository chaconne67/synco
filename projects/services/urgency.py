"""긴급도 자동 산정 로직."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    ProjectStatus,
    Submission,
)

# Closed statuses — no urgency
CLOSED_STATUSES = {
    ProjectStatus.CLOSED_SUCCESS,
    ProjectStatus.CLOSED_FAIL,
    ProjectStatus.CLOSED_CANCEL,
    ProjectStatus.ON_HOLD,
    ProjectStatus.PENDING_APPROVAL,
}


def collect_all_actions(project: Project) -> list[dict]:
    """
    프로젝트의 모든 긴급도 액션을 수집.

    Returns list of dicts with keys: priority, level, label, detail, project, related_object.
    Returns empty list if project is closed/on_hold/pending.
    """
    if project.status in CLOSED_STATUSES:
        return []

    now = timezone.now()
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=(6 - today.weekday()))

    actions: list[dict] = []

    # --- Priority 1: 재컨택 예정일이 오늘이거나 과거 ---
    overdue_contacts = (
        Contact.objects.filter(
            project=project,
            next_contact_date__lte=today,
        )
        .exclude(
            result=Contact.Result.RESERVED,
        )
        .select_related("candidate")
    )

    for contact in overdue_contacts:
        days_overdue = (today - contact.next_contact_date).days
        detail = "오늘" if days_overdue == 0 else f"D+{days_overdue} 지연"
        actions.append(
            {
                "priority": 1,
                "level": "red",
                "label": "재컨택",
                "detail": detail,
                "project": project,
                "related_object": contact,
            }
        )

    # --- Priority 2: 면접 일정이 오늘~내일 ---
    imminent_interviews = Interview.objects.filter(
        submission__project=project,
        scheduled_at__date__gte=today,
        scheduled_at__date__lte=tomorrow,
        result="대기",
    ).select_related("submission__candidate")

    for interview in imminent_interviews:
        actions.append(
            {
                "priority": 2,
                "level": "red",
                "label": "면접 임박",
                "detail": f"{interview.round}차 면접 {interview.scheduled_at.strftime('%m/%d')}",
                "project": project,
                "related_object": interview,
            }
        )

    # --- Priority 3: 서류 제출 후 검토 대기 2일 이상 ---
    pending_submissions = Submission.objects.filter(
        project=project,
        status="제출",
        submitted_at__lte=now - timedelta(days=2),
    ).select_related("candidate")

    for sub in pending_submissions:
        days_waiting = (now - sub.submitted_at).days
        actions.append(
            {
                "priority": 3,
                "level": "red",
                "label": "서류 검토 필요",
                "detail": f"대기: {days_waiting}일",
                "project": project,
                "related_object": sub,
            }
        )

    # --- Priority 4: 잠금 만료 1일 이내 ---
    expiring_locks = Contact.objects.filter(
        project=project,
        result=Contact.Result.RESERVED,
        locked_until__gt=now,
        locked_until__lte=now + timedelta(days=1),
    ).select_related("candidate")

    for contact in expiring_locks:
        actions.append(
            {
                "priority": 4,
                "level": "red",
                "label": "컨택 잠금 만료 임박",
                "detail": f"만료: {contact.locked_until.strftime('%m/%d %H:%M')}",
                "project": project,
                "related_object": contact,
            }
        )

    # --- Priority 5: 면접 일정 이번 주 ---
    week_interviews = Interview.objects.filter(
        submission__project=project,
        scheduled_at__date__gt=tomorrow,
        scheduled_at__date__lte=week_end,
        result="대기",
    ).select_related("submission__candidate")

    for interview in week_interviews:
        actions.append(
            {
                "priority": 5,
                "level": "yellow",
                "label": "면접 예정",
                "detail": f"{interview.round}차 {interview.scheduled_at.strftime('%m/%d (%a)')}",
                "project": project,
                "related_object": interview,
            }
        )

    # --- Priority 6: 재컨택 예정 이번 주 ---
    week_recontacts = (
        Contact.objects.filter(
            project=project,
            next_contact_date__gt=today,
            next_contact_date__lte=week_end,
        )
        .exclude(
            result=Contact.Result.RESERVED,
        )
        .select_related("candidate")
    )

    for contact in week_recontacts:
        actions.append(
            {
                "priority": 6,
                "level": "yellow",
                "label": "재컨택 예정",
                "detail": f"{contact.next_contact_date.strftime('%m/%d')} 예정",
                "project": project,
                "related_object": contact,
            }
        )

    # --- Priority 7: 오퍼 회신 대기 7일 이상 ---
    stale_offers = Offer.objects.filter(
        submission__project=project,
        status="협상중",
        created_at__lte=now - timedelta(days=7),
    )

    for offer in stale_offers:
        days_waiting = (now - offer.created_at).days
        actions.append(
            {
                "priority": 7,
                "level": "yellow",
                "label": "오퍼 회신 대기",
                "detail": f"D+{days_waiting}",
                "project": project,
                "related_object": offer,
            }
        )

    # --- Priority 8: 신규 프로젝트 (D+3 이내) ---
    if project.status == ProjectStatus.NEW and project.days_elapsed <= 3:
        actions.append(
            {
                "priority": 8,
                "level": "green",
                "label": "서칭 시작 필요",
                "detail": f"신규: D+{project.days_elapsed}",
                "project": project,
                "related_object": None,
            }
        )

    # --- Priority 9: 기타 진행 중 ---
    if not actions:
        actions.append(
            {
                "priority": 9,
                "level": "green",
                "label": "정상 진행",
                "detail": project.get_status_display(),
                "project": project,
                "related_object": None,
            }
        )

    return actions


def compute_project_urgency(project: Project) -> dict | None:
    """
    프로젝트의 가장 높은 긴급도 액션 1개를 결정.

    Returns dict or None if project is closed/on_hold/pending.
    """
    actions = collect_all_actions(project)
    if not actions:
        return None
    return min(actions, key=lambda a: a["priority"])
