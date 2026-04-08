"""대시보드 데이터 집계 서비스."""

from __future__ import annotations


from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import Membership, Organization, User
from projects.models import (
    Contact,
    Interview,
    Project,
    ProjectApproval,
    ProjectStatus,
    Submission,
)
from projects.services.urgency import collect_all_actions

INACTIVE_STATUSES = {
    ProjectStatus.CLOSED_SUCCESS,
    ProjectStatus.CLOSED_FAIL,
    ProjectStatus.CLOSED_CANCEL,
    ProjectStatus.ON_HOLD,
    ProjectStatus.PENDING_APPROVAL,
}

PIPELINE_STATUSES = [
    ProjectStatus.NEW,
    ProjectStatus.SEARCHING,
    ProjectStatus.RECOMMENDING,
    ProjectStatus.INTERVIEWING,
    ProjectStatus.NEGOTIATING,
]


def _my_active_projects(user: User, org: Organization) -> QuerySet:
    """현재 사용자의 활성 프로젝트."""
    return (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .exclude(status__in=INACTIVE_STATUSES)
        .distinct()
    )


def get_today_actions(user: User, org: Organization) -> list[dict]:
    """긴급도 자동 산정 후 오늘의 액션 목록 반환 (빨강 only)."""
    projects = _my_active_projects(user, org)

    actions = []
    for project in projects:
        all_actions = collect_all_actions(project)
        actions.extend(a for a in all_actions if a["level"] == "red")

    actions.sort(key=lambda a: a["priority"])
    return actions


def get_weekly_schedule(user: User, org: Organization) -> list[dict]:
    """이번 주 일정 (노랑 level actions)."""
    projects = _my_active_projects(user, org)

    actions = []
    for project in projects:
        all_actions = collect_all_actions(project)
        actions.extend(a for a in all_actions if a["level"] == "yellow")

    actions.sort(key=lambda a: a["priority"])
    return actions


def get_pipeline_summary(user: User, org: Organization) -> dict:
    """내 프로젝트 상태별 카운트 + 이번 달 클로즈 건수."""
    my_projects = (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .distinct()
    )

    status_counts = {}
    for status_value in PIPELINE_STATUSES:
        status_counts[status_value] = my_projects.filter(status=status_value).count()

    total_active = sum(status_counts.values())

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_closed = my_projects.filter(
        status=ProjectStatus.CLOSED_SUCCESS,
        updated_at__gte=month_start,
    ).count()

    return {
        "status_counts": status_counts,
        "total_active": total_active,
        "month_closed": month_closed,
    }


def get_recent_activities(user: User, org: Organization, limit: int = 10) -> list[dict]:
    """최근 활동 로그 반환.

    Aggregates recent contacts, project creations, and submissions
    from user's projects, sorted by time descending.
    """
    my_projects = (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .distinct()
    )
    project_ids = list(my_projects.values_list("pk", flat=True))
    activities: list[dict] = []

    recent_contacts = (
        Contact.objects.filter(project_id__in=project_ids)
        .exclude(result=Contact.Result.RESERVED)
        .select_related("candidate", "project")
        .order_by("-created_at")[:limit]
    )
    for contact in recent_contacts:
        activities.append(
            {
                "type": "contact",
                "timestamp": contact.created_at,
                "description": (
                    f"{contact.candidate.name} 컨택 기록 추가 ({contact.project.title})"
                ),
            }
        )

    recent_projects = (
        Project.objects.filter(pk__in=project_ids)
        .select_related("client")
        .order_by("-created_at")[:limit]
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

    recent_subs = (
        Submission.objects.filter(project_id__in=project_ids)
        .select_related("candidate", "project")
        .order_by("-created_at")[:limit]
    )
    for sub in recent_subs:
        activities.append(
            {
                "type": "submission",
                "timestamp": sub.created_at,
                "description": (
                    f"{sub.candidate.name} 제출서류 생성 ({sub.project.title})"
                ),
            }
        )

    activities.sort(key=lambda a: a["timestamp"], reverse=True)
    return activities[:limit]


def get_team_summary(admin_user: User, org: Organization) -> dict:
    """팀 전체 현황 + KPI (OWNER 전용).

    Fix I-R1-02: Only owner/consultant roles. Use Contact.consultant
    and Submission.consultant for per-person counts to avoid double-counting.
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
            .exclude(status__in=INACTIVE_STATUSES)
            .distinct()
            .count()
        )

        # Per-consultant counts based on consultant FK (no double-counting)
        contact_count = (
            Contact.objects.filter(
                project__organization=org,
                consultant=user,
            )
            .exclude(result=Contact.Result.RESERVED)
            .count()
        )

        submission_count = Submission.objects.filter(
            project__organization=org,
            consultant=user,
        ).count()

        interview_count = Interview.objects.filter(
            submission__project__organization=org,
            submission__consultant=user,
        ).count()

        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        closed_count = (
            Project.objects.filter(organization=org)
            .filter(Q(assigned_consultants=user) | Q(created_by=user))
            .filter(status=ProjectStatus.CLOSED_SUCCESS, updated_at__gte=month_start)
            .distinct()
            .count()
        )

        consultants.append(
            {
                "user": user,
                "active": active_count,
                "contacts": contact_count,
                "submissions": submission_count,
                "interviews": interview_count,
                "closed": closed_count,
            }
        )

    # KPI from org-wide distinct records
    total_contacts = (
        Contact.objects.filter(
            project__organization=org,
        )
        .exclude(result=Contact.Result.RESERVED)
        .count()
    )

    total_submissions = Submission.objects.filter(
        project__organization=org,
    ).count()

    total_interviews = Interview.objects.filter(
        submission__project__organization=org,
    ).count()

    contact_to_submission = (
        round(total_submissions / total_contacts * 100) if total_contacts > 0 else 0
    )
    submission_to_interview = (
        round(total_interviews / total_submissions * 100)
        if total_submissions > 0
        else 0
    )

    return {
        "consultants": consultants,
        "kpi": {
            "contact_to_submission": contact_to_submission,
            "submission_to_interview": submission_to_interview,
        },
    }


def get_pending_approvals(org: Organization) -> QuerySet:
    """미처리 승인 요청 목록 (OWNER 전용)."""
    return ProjectApproval.objects.filter(
        project__organization=org,
        status=ProjectApproval.Status.PENDING,
    ).select_related("project", "requested_by")
