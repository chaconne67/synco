"""Shared helpers for split project view modules."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Max

from accounts.services.scope import get_scoped_object_or_404

from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
    DEFAULT_MASKING_CONFIG,
    Interview,
    Project,
    ProjectApproval,
    Submission,
    SubmissionDraft,
)


def _has_pending_approval(project):
    """Check if the project has a pending approval (replaces PENDING_APPROVAL status)."""
    return ProjectApproval.objects.filter(
        project=project, status=ProjectApproval.Status.PENDING
    ).exists()


def _filter_params_string(request, exclude=None):
    """Build query string from current filter params (scope, client, status, sort)."""
    exclude = exclude or []
    params = []
    for key in ("scope", "client", "status", "sort"):
        if key in exclude:
            continue
        val = request.GET.get(key, "")
        if val:
            params.append(f"{key}={val}")
    return "&".join(params)


def _build_tab_context(project):
    """Build tab_counts and tab_latest for project detail template.

    Submission은 Application 경유(related_name 'submission' 단수). Project에서 직접 역참조 불가.
    """
    submissions_qs = Submission.objects.filter(application__project=project)
    tab_counts = {
        "applications": Application.objects.filter(project=project).count(),
        "submissions": submissions_qs.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
    }
    tab_latest = {
        "applications": Application.objects.filter(project=project).aggregate(
            latest=Max("created_at")
        )["latest"],
        "submissions": submissions_qs.aggregate(latest=Max("created_at"))["latest"],
        "interviews": Interview.objects.filter(submission__project=project).aggregate(
            latest=Max("created_at")
        )["latest"],
    }
    return tab_counts, tab_latest


def _build_overview_context(project):
    """개요 탭 공통 컨텍스트 (Application-based)."""
    active_apps = Application.objects.filter(
        project=project, dropped_at__isnull=True, hired_at__isnull=True
    )
    funnel = {
        "applications": Application.objects.filter(project=project).count(),
        "active": active_apps.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
    }

    recent_applications = (
        Application.objects.filter(project=project)
        .select_related("candidate")
        .order_by("-created_at")[:3]
    )
    recent_submissions = project.submissions.select_related(
        "candidate", "consultant"
    ).order_by("-created_at")[:2]

    consultants = project.assigned_consultants.all()

    # P10: posting data
    posting_sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in posting_sites)

    return {
        "funnel": funnel,
        "recent_applications": recent_applications,
        "recent_submissions": recent_submissions,
        "consultants": consultants,
        "posting_sites": posting_sites,
        "total_applicants": total_applicants,
    }


def _get_draft_context(request, pk, sub_pk):
    """Draft 뷰 공통: project + submission + draft(get_or_create)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submission = get_scoped_object_or_404(
        Submission, request.user, pk=sub_pk, action_item__application__project=project
    )
    draft, _created = SubmissionDraft.objects.get_or_create(
        submission=submission,
        defaults={"masking_config": DEFAULT_MASKING_CONFIG.copy()},
    )
    return project, submission, draft


def _create_receive_resume_action(application, actor, *, done, note, due_days=0):
    """Phase B 헬퍼: receive_resume ActionType 으로 ActionItem 생성.

    ToDoList 모델: due_days=0 이면 마감 기한 없음 (대기 항목). done=True 면 즉시 완료.
    """
    from django.utils import timezone

    at = ActionType.objects.filter(code="receive_resume").first()
    if not at:
        return None
    now = timezone.now()
    due = now + timedelta(days=due_days) if due_days else None
    return ActionItem.objects.create(
        application=application,
        action_type=at,
        title=at.label_ko,
        note=note,
        status=ActionItemStatus.DONE if done else ActionItemStatus.PENDING,
        completed_at=now if done else None,
        scheduled_at=due,
        due_at=due,
        assigned_to=actor,
        created_by=actor,
    )
