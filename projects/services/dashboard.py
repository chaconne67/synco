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


def get_overdue_actions(user: User, org: Organization):
    """해당 사용자의 마감 지난 액션."""
    now = timezone.now()
    return ActionItem.objects.filter(
        assigned_to=user,
        application__project__organization=org,
        status=ActionItemStatus.PENDING,
        due_at__lt=now,
    ).select_related("application__project", "application__candidate", "action_type")


def get_upcoming_actions(user: User, org: Organization, days=3):
    """해당 사용자의 3일 내 예정 액션 (scheduled_at 또는 due_at 기준)."""
    now = timezone.now()
    soon = now + timedelta(days=days)
    return (
        ActionItem.objects.filter(
            assigned_to=user,
            application__project__organization=org,
            status=ActionItemStatus.PENDING,
        )
        .filter(
            Q(scheduled_at__gte=now, scheduled_at__lte=soon)
            | Q(due_at__gte=now, due_at__lte=soon)
        )
        .select_related("application__project", "application__candidate", "action_type")
        .distinct()
    )


def get_project_kanban_cards(org: Organization):
    """2-phase 칸반에 필요한 카드 데이터."""
    now = timezone.now()
    projects = (
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

        card = {
            "project": project,
            "active_count": project.active_count,
            "pending_actions_count": pending_count,
            "overdue_count": overdue_count,
            "deadline": project.deadline,
            "days_until_deadline": (
                (project.deadline - now.date()).days if project.deadline else None
            ),
        }

        if project.status == ProjectStatus.CLOSED:
            cards["closed"].append(card)
        else:
            cards[project.phase].append(card)

    return cards


def get_pending_approvals(org: Organization):
    """미처리 승인 요청 목록 (OWNER 전용)."""
    from projects.models import ProjectApproval

    return ProjectApproval.objects.filter(
        project__organization=org,
        status=ProjectApproval.Status.PENDING,
    ).select_related("project", "requested_by")
