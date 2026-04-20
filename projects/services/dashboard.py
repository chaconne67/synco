"""대시보드 데이터 집계 서비스.

Phase 2b: Rewritten with Application/ActionItem-based queries.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Organization, User
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Project,
    ProjectPhase,
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


def get_dashboard_context(org: Organization, user: User, membership) -> dict:
    """대시보드 카드 전체 컨텍스트.

    Phase 2a: S1-1 Monthly Success, S1-3 Project Status,
              S2-1 Team Performance, S3 Weekly/Monthly Calendar.
    Phase 2b 카드(S1-2 Revenue, S2-2 Recent Activity)는 하드코딩 유지.
    """
    scope_owner = membership.role == "owner"
    return {
        "monthly_success": None,
        "project_status": None,
        "team_performance": None,
        "weekly_schedule": None,
        "monthly_calendar": None,
        "_scope_owner": scope_owner,
    }


def _scope_projects(org: Organization, user: User, scope_owner: bool):
    """권한 스코프 공통 쿼리셋. owner=조직 전체, 아니면 본인 담당만."""
    qs = Project.objects.filter(organization=org)
    if not scope_owner:
        qs = qs.filter(assigned_consultants=user)
    return qs

