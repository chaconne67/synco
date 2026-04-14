"""Approval state transition service for project collision workflow."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from projects.models import Notification, Project, ProjectApproval, ProjectStatus


class InvalidApprovalTransition(Exception):
    """Attempted an invalid approval state transition."""

    pass


# Allowed transitions from current status
APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    ProjectApproval.Status.PENDING: {
        ProjectApproval.Status.APPROVED,
        ProjectApproval.Status.JOINED,
        ProjectApproval.Status.REJECTED,
    },
    # Terminal states -- no further transitions allowed
}


def _check_transition(approval: ProjectApproval, target_status: str) -> None:
    """Validate that the transition is allowed."""
    allowed = APPROVAL_TRANSITIONS.get(approval.status, set())
    if target_status not in allowed:
        raise InvalidApprovalTransition(
            f"'{approval.get_status_display()}' 상태에서는 "
            f"'{target_status}' 전환이 불가능합니다."
        )


@transaction.atomic
def approve_project(approval: ProjectApproval, admin_user) -> None:
    """Approve: pending -> approved, project status -> new."""
    approval = ProjectApproval.objects.select_for_update().get(pk=approval.pk)
    _check_transition(approval, ProjectApproval.Status.APPROVED)

    approval.status = ProjectApproval.Status.APPROVED
    approval.decided_by = admin_user
    approval.decided_at = timezone.now()
    approval.save(update_fields=["status", "decided_by", "decided_at"])

    project = approval.project
    project.status = ProjectStatus.OPEN
    project.save(update_fields=["status"])

    # Notify requester
    Notification.objects.create(
        recipient=approval.requested_by,
        type=Notification.Type.APPROVAL_REQUEST,
        title="프로젝트가 승인되었습니다",
        body=f"'{project.title}' 프로젝트가 승인되었습니다.",
    )


@transaction.atomic
def reject_project(
    approval: ProjectApproval,
    admin_user,
    response_text: str = "",
) -> None:
    """Reject: pending -> rejected, delete project."""
    approval = ProjectApproval.objects.select_for_update().get(pk=approval.pk)
    _check_transition(approval, ProjectApproval.Status.REJECTED)

    project = approval.project
    project_title = project.title
    requester = approval.requested_by

    approval.status = ProjectApproval.Status.REJECTED
    approval.decided_by = admin_user
    approval.decided_at = timezone.now()
    approval.admin_response = response_text
    approval.save(
        update_fields=["status", "decided_by", "decided_at", "admin_response"]
    )

    # Delete the pending project (safe -- pending_approval blocks downstream data)
    _safe_delete_pending_project(project)

    # Notify requester
    body = f"'{project_title}' 프로젝트가 반려되었습니다."
    if response_text:
        body += f"\n사유: {response_text}"
    Notification.objects.create(
        recipient=requester,
        type=Notification.Type.APPROVAL_REQUEST,
        title="프로젝트가 반려되었습니다",
        body=body,
    )


@transaction.atomic
def merge_project(
    approval: ProjectApproval,
    admin_user,
    merge_target: Project | None = None,
) -> None:
    """Merge: pending -> joined, add requester to target, delete pending project."""
    approval = ProjectApproval.objects.select_for_update().get(pk=approval.pk)
    _check_transition(approval, ProjectApproval.Status.JOINED)

    target = merge_target or approval.conflict_project
    if target is None:
        raise InvalidApprovalTransition("합류 대상 프로젝트가 지정되지 않았습니다.")

    project = approval.project
    requester = approval.requested_by

    approval.status = ProjectApproval.Status.JOINED
    approval.decided_by = admin_user
    approval.decided_at = timezone.now()
    approval.save(update_fields=["status", "decided_by", "decided_at"])

    # Add requester to target project
    target.assigned_consultants.add(requester)

    # Delete the pending project
    _safe_delete_pending_project(project)

    # Notify requester
    Notification.objects.create(
        recipient=requester,
        type=Notification.Type.APPROVAL_REQUEST,
        title="기존 프로젝트에 합류되었습니다",
        body=f"'{target.title}' 프로젝트에 합류되었습니다.",
    )


def send_admin_message(
    approval: ProjectApproval,
    admin_user,
    message: str,
) -> None:
    """Send message without changing status."""
    if approval.status != ProjectApproval.Status.PENDING:
        raise InvalidApprovalTransition("대기 상태에서만 메시지를 보낼 수 있습니다.")
    approval.admin_response = message
    approval.save(update_fields=["admin_response"])

    Notification.objects.create(
        recipient=approval.requested_by,
        type=Notification.Type.APPROVAL_REQUEST,
        title="승인 요청에 대한 메시지가 있습니다",
        body=f"관리자 메시지: {message}",
    )


@transaction.atomic
def cancel_approval(approval: ProjectApproval) -> None:
    """Cancel: delete both approval and project."""
    project = approval.project
    approval.delete()
    if project:
        _safe_delete_pending_project(project)


def _safe_delete_pending_project(project: Project) -> None:
    """Delete a pending_approval project. Raises if downstream data exists."""
    if project.applications.exists():
        raise InvalidApprovalTransition(
            "하위 데이터(지원)가 존재하여 삭제할 수 없습니다."
        )
    project.delete()
