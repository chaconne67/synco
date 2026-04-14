"""대시보드 데이터 집계 서비스.

Phase 1: Contact model deleted, ProjectStatus changed to 2-state.
Phase 2-6: Will be rewritten with Application/ActionItem-based queries.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import Membership, Organization, User
from projects.models import (
    Interview,
    Project,
    ProjectApproval,
    ProjectStatus,
    Submission,
)


def _my_active_projects(user: User, org: Organization) -> QuerySet:
    """현재 사용자의 활성 프로젝트."""
    return (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .filter(status=ProjectStatus.OPEN)
        .distinct()
    )


def get_today_actions(user: User, org: Organization) -> list[dict]:
    """긴급도 자동 산정 후 오늘의 액션 목록 반환.

    Phase 1 stub — urgency system will be rebuilt with ActionItem.
    """
    return []


def get_weekly_schedule(user: User, org: Organization) -> list[dict]:
    """이번 주 일정. Phase 1 stub."""
    return []


def get_pipeline_summary(user: User, org: Organization) -> dict:
    """내 프로젝트 상태별 카운트.

    Phase 1: Simplified to open/closed counts only.
    """
    my_projects = (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .distinct()
    )

    open_count = my_projects.filter(status=ProjectStatus.OPEN).count()
    closed_count = my_projects.filter(status=ProjectStatus.CLOSED).count()

    return {
        "status_counts": {ProjectStatus.OPEN: open_count},
        "total_active": open_count,
        "month_closed": closed_count,
    }


def get_recent_activities(user: User, org: Organization, limit: int = 10) -> list[dict]:
    """최근 활동 로그 반환.

    Phase 1: Contact removed, Submission no longer has project/candidate FK.
    Only recent project creations are returned.
    """
    my_projects = (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .distinct()
    )
    activities: list[dict] = []

    recent_projects = (
        my_projects.select_related("client").order_by("-created_at")[:limit]
    )
    for proj in recent_projects:
        client_name = proj.client.name if proj.client else ""
        activities.append(
            {
                "type": "project",
                "timestamp": proj.created_at,
                "description": f"{client_name} {proj.title} 프로젝트 등록",
            }
        )

    activities.sort(key=lambda a: a["timestamp"], reverse=True)
    return activities[:limit]


def get_team_summary(admin_user: User, org: Organization) -> dict:
    """팀 전체 현황 + KPI (OWNER 전용).

    Phase 1: Contact model deleted. Simplified to project counts only.
    """
    members = Membership.objects.filter(
        organization=org,
        role__in=[Membership.Role.OWNER, Membership.Role.CONSULTANT],
    ).select_related("user")

    consultants = []

    for member in members:
        user = member.user

        active_count = (
            Project.objects.filter(organization=org)
            .filter(Q(assigned_consultants=user) | Q(created_by=user))
            .filter(status=ProjectStatus.OPEN)
            .distinct()
            .count()
        )

        consultants.append(
            {
                "user": user,
                "active": active_count,
                "contacts": 0,
                "submissions": 0,
                "interviews": 0,
                "closed": 0,
            }
        )

    return {
        "consultants": consultants,
        "kpi": {
            "contact_to_submission": 0,
            "submission_to_interview": 0,
        },
    }


def get_pending_approvals(org: Organization) -> QuerySet:
    """미처리 승인 요청 목록 (OWNER 전용)."""
    return ProjectApproval.objects.filter(
        project__organization=org,
        status=ProjectApproval.Status.PENDING,
    ).select_related("project", "requested_by")
