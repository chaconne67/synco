"""대시보드 데이터 집계 서비스.

Phase 2b: Rewritten with Application/ActionItem-based queries.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Membership, Organization, User
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Interview,
    Project,
    ProjectPhase,
    ProjectResult,
    ProjectStatus,
)


def get_today_actions(user: User, org: Organization):
    """해당 사용자의 오늘 할 일 (scheduled_at 오늘 또는 due_at 오늘, overdue 제외)."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    return (
        ActionItem.objects.filter(
            assigned_to=user,
            application__project__organization=org,
            status=ActionItemStatus.PENDING,
        )
        .filter(
            Q(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
            | Q(due_at__gte=max(now, today_start), due_at__lt=today_end)
        )
        .select_related("application__project", "application__candidate", "action_type")
    )


def _sweep_overdue_projects(org: Organization):
    """마감 경과 OPEN 프로젝트를 자동으로 실패 종료.

    정책: deadline < today + hired Application 없음 → status=CLOSED, result=fail.
    관리 커맨드와 동일 로직, 칸반 조회 시 lazy 실행.
    """
    today = timezone.now().date()
    now = timezone.now()

    overdue = (
        Project.objects.filter(
            organization=org,
            status=ProjectStatus.OPEN,
            deadline__lt=today,
        )
        .exclude(applications__hired_at__isnull=False)
    )
    note_suffix = f"\n\n[AUTO-CLOSE {today.isoformat()}] 마감일 경과로 자동 종료 (실패)"
    from projects.models import Application
    for p in overdue:
        Project.objects.filter(pk=p.pk).update(
            status=ProjectStatus.CLOSED,
            result="fail",
            closed_at=now,
            note=(p.note or "") + note_suffix,
        )
        Application.objects.filter(
            project=p, dropped_at__isnull=True, hired_at__isnull=True
        ).update(
            dropped_at=now,
            drop_reason="other",
            drop_note="프로젝트 마감일 경과로 자동 종료",
        )


def get_project_kanban_cards(
    org: Organization,
    *,
    consultant_id=None,
    client_id=None,
    search=None,
    sort_searching="asc",
    sort_screening="asc",
    sort_closed="desc",
):
    """2-phase 칸반에 필요한 카드 데이터.

    필터:
    - consultant_id: 담당자 UUID (assigned_consultants 중)
    - client_id: 고객사 UUID
    - search: title 또는 client.name ilike
    """
    # 칸반 렌더 직전에 마감 경과 프로젝트 자동 종료 (Stale auto-close)
    _sweep_overdue_projects(org)

    now = timezone.now()
    qs = (
        Project.objects.filter(organization=org)
        .annotate(
            active_count=Count(
                "applications",
                filter=Q(
                    applications__dropped_at__isnull=True,
                    applications__hired_at__isnull=True,
                ),
            ),
        )
        .select_related("client")
        .prefetch_related("assigned_consultants")
    )
    if consultant_id:
        qs = qs.filter(assigned_consultants__id=consultant_id)
    if client_id:
        qs = qs.filter(client_id=client_id)
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(client__name__icontains=search))
    projects = qs.distinct()

    cards = {
        ProjectPhase.SEARCHING: [],
        ProjectPhase.SCREENING: [],
        "closed": [],
    }

    for project in projects:
        pending_actions = ActionItem.objects.filter(
            application__project=project,
            status=ActionItemStatus.PENDING,
        )
        overdue_count = pending_actions.filter(due_at__lt=now).count()
        pending_count = pending_actions.count()

        # closed + success 프로젝트는 입사자 이름 표시용으로 hired Application 조회
        hired_candidate = None
        if project.status == ProjectStatus.CLOSED and project.result == "success":
            hired_app = (
                project.applications.filter(hired_at__isnull=False)
                .select_related("candidate")
                .first()
            )
            if hired_app:
                hired_candidate = hired_app.candidate

        card = {
            "project": project,
            "active_count": project.active_count,
            "pending_actions_count": pending_count,
            "overdue_count": overdue_count,
            "deadline": project.deadline,
            "days_until_deadline": (
                (project.deadline - now.date()).days if project.deadline else None
            ),
            "hired_candidate": hired_candidate,
        }

        if project.status == ProjectStatus.CLOSED:
            cards["closed"].append(card)
        else:
            cards[project.phase].append(card)

    # 정렬 정책 (컬럼별 독립):
    # - OPEN 컬럼: created_at 기준. 기본 asc(오래된 것 상단).
    # - CLOSED 컬럼: closed_at 기준. 기본 desc(최근 종료건 먼저).
    cards[ProjectPhase.SEARCHING].sort(
        key=lambda c: c["project"].created_at,
        reverse=(sort_searching == "desc"),
    )
    cards[ProjectPhase.SCREENING].sort(
        key=lambda c: c["project"].created_at,
        reverse=(sort_screening == "desc"),
    )
    cards["closed"].sort(
        key=lambda c: c["project"].closed_at or c["project"].updated_at,
        reverse=(sort_closed == "desc"),
    )

    return cards


def _monthly_success(org, user, scope_owner):
    """S1-1 Monthly Success: 이번 달 성공·진행중·성공률."""
    now_local = timezone.localtime()
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = _scope_projects(org, user, scope_owner)

    closed_this_month = qs.filter(
        status=ProjectStatus.CLOSED,
        closed_at__gte=month_start,
    )
    success = closed_this_month.filter(result=ProjectResult.SUCCESS).count()
    fail = closed_this_month.filter(result=ProjectResult.FAIL).count()
    active = qs.filter(status=ProjectStatus.OPEN).count()
    total = success + fail
    return {
        "success_count": success,
        "active_count": active,
        "success_rate": round(success / total * 100) if total else None,
    }


def _project_status_counts(org, user, scope_owner):
    """S1-3 Project Status: searching/screening/closed 누적 개수."""
    qs = _scope_projects(org, user, scope_owner)
    return {
        "searching": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SEARCHING
        ).count(),
        "screening": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SCREENING
        ).count(),
        "closed": qs.filter(status=ProjectStatus.CLOSED).count(),
    }


_ROLE_LABEL_KO = {
    "owner": "대표",
    "consultant": "컨설턴트",
}


def _display_name(user) -> str:
    """한글 이름 표시. last+first → get_full_name → username."""
    parts = (user.last_name or "").strip() + (user.first_name or "").strip()
    if parts:
        return parts
    full = (user.get_full_name() or "").strip()
    if full:
        return full
    return user.username


def _progress_color(rate):
    """S2-1 progress bar 색상 클래스. rate=None → default."""
    if rate is None:
        return ""
    if rate >= 80:
        return "success"
    if rate >= 60:
        return ""
    return "info"


def _team_performance(org):
    """S2-1 Team Performance: owner+consultant 전체, 누적 성공률 desc.

    Viewer 제외. 표본 없는 멤버(rate=None)는 맨 아래.
    """
    memberships = Membership.objects.filter(
        organization=org,
        role__in=["owner", "consultant"],
        status="active",
    ).select_related("user")
    rows = []
    for m in memberships:
        user = m.user
        assigned = user.assigned_projects.filter(organization=org)
        active_count = assigned.filter(status=ProjectStatus.OPEN).count()
        closed = assigned.filter(status=ProjectStatus.CLOSED)
        closed_total = closed.count()
        success_count = closed.filter(result=ProjectResult.SUCCESS).count()
        rate = round(success_count / closed_total * 100) if closed_total else None

        rows.append({
            "username": user.username,
            "display_name": _display_name(user),
            "role_label": _ROLE_LABEL_KO.get(m.role, m.role),
            "active_count": active_count,
            "success_rate": rate,
            "progress_color": _progress_color(rate),
        })

    # sort: rate desc NULLS LAST
    rows.sort(key=lambda r: (r["success_rate"] is None, -(r["success_rate"] or 0)))
    return rows


# action_type codes treated as 고객사-related → warning label color in weekly schedule
_CLIENT_FACING_CODES = {"submit_to_client", "pre_meeting"}


def _week_range():
    now = timezone.localtime()
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    next_monday = monday + timedelta(days=7)
    return monday, next_monday


def _weekly_schedule(org, user, scope_owner, limit: int = 5):
    """S3 Weekly Schedule: 이번 주 Interview + ActionItem 합집합, 시간 asc."""
    monday, next_monday = _week_range()

    interviews = Interview.objects.filter(
        action_item__application__project__organization=org,
        scheduled_at__gte=monday,
        scheduled_at__lt=next_monday,
    ).select_related(
        "action_item__application__candidate",
        "action_item__application__project__client",
    )
    actions = (
        ActionItem.objects.filter(
            application__project__organization=org,
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        )
        .exclude(action_type__code="interview_round")
        .select_related(
            "action_type",
            "application__project__client",
        )
    )

    if not scope_owner:
        interviews = interviews.filter(
            action_item__application__project__assigned_consultants=user
        )
        actions = actions.filter(assigned_to=user)

    events = []

    for iv in interviews:
        candidate = iv.action_item.application.candidate
        events.append({
            "scheduled_at": iv.scheduled_at,
            "label_color": "info",
            "title": f"{iv.round}차 면접",
            "subtitle": f"후보자: {candidate.name} · {iv.location or '-'}",
        })

    for ai in actions:
        code = ai.action_type.code
        color = "warning" if code in _CLIENT_FACING_CODES else "ink3"
        proj = ai.application.project
        client = proj.client
        events.append({
            "scheduled_at": ai.scheduled_at,
            "label_color": color,
            "title": ai.title,
            "subtitle": f"{proj.title} · {client.name}",
        })

    events.sort(key=lambda e: e["scheduled_at"])
    return events[:limit]


def get_dashboard_context(org: Organization, user: User, membership) -> dict:
    """대시보드 카드 전체 컨텍스트.

    Phase 2a: S1-1 Monthly Success, S1-3 Project Status,
              S2-1 Team Performance, S3 Weekly/Monthly Calendar.
    Phase 2b 카드(S1-2 Revenue, S2-2 Recent Activity)는 하드코딩 유지.
    """
    scope_owner = membership.role == "owner"
    return {
        "monthly_success": _monthly_success(org, user, scope_owner),
        "project_status": _project_status_counts(org, user, scope_owner),
        "team_performance": _team_performance(org),
        "weekly_schedule": _weekly_schedule(org, user, scope_owner),
        "monthly_calendar": None,
        "_scope_owner": scope_owner,
    }


def _scope_projects(org: Organization, user: User, scope_owner: bool):
    """권한 스코프 공통 쿼리셋. owner=조직 전체, 아니면 본인 담당만."""
    qs = Project.objects.filter(organization=org)
    if not scope_owner:
        qs = qs.filter(assigned_consultants=user)
    return qs

