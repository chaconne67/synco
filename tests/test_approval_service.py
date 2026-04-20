"""Tests for projects/services/approval.py."""

import pytest

from projects.models import (
    Notification,
    Project,
    ProjectApproval,
    ProjectStatus,
)
from projects.services.approval import (
    InvalidApprovalTransition,
    approve_project,
    cancel_approval,
    merge_project,
    reject_project,
    send_admin_message,
)


@pytest.fixture
def pending_project(db, client_company, staff_user):
    return Project.objects.create(
        client=client_company,
        title="승인대기 프로젝트",
        status=ProjectStatus.OPEN,
        created_by=staff_user,
    )


@pytest.fixture
def conflict_project(db, client_company, boss_user):
    return Project.objects.create(
        client=client_company,
        title="충돌 프로젝트",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )


@pytest.fixture
def approval(db, pending_project, staff_user):
    return ProjectApproval.objects.create(
        project=pending_project,
        requested_by=staff_user,
        status=ProjectApproval.Status.PENDING,
    )


# ---------------------------------------------------------------------------
# approve_project
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_approve_project_happy_path(approval, boss_user, pending_project):
    approve_project(approval, admin_user=boss_user)

    approval.refresh_from_db()
    assert approval.status == ProjectApproval.Status.APPROVED
    assert approval.decided_by == boss_user
    assert approval.decided_at is not None

    pending_project.refresh_from_db()
    assert pending_project.status == ProjectStatus.OPEN


@pytest.mark.django_db
def test_approve_project_creates_notification(approval, boss_user, staff_user):
    approve_project(approval, admin_user=boss_user)

    notif = Notification.objects.filter(recipient=staff_user).last()
    assert notif is not None
    assert "승인" in notif.title


# ---------------------------------------------------------------------------
# reject_project
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reject_project_happy_path(approval, boss_user, pending_project):
    project_pk = pending_project.pk
    reject_project(approval, admin_user=boss_user, response_text="중복 포지션")

    approval.refresh_from_db()
    assert approval.status == ProjectApproval.Status.REJECTED
    assert approval.admin_response == "중복 포지션"
    # Pending project should be deleted
    assert not Project.objects.filter(pk=project_pk).exists()


@pytest.mark.django_db
def test_reject_project_creates_notification(approval, boss_user, staff_user, pending_project):
    reject_project(approval, admin_user=boss_user)

    notif = Notification.objects.filter(recipient=staff_user).last()
    assert notif is not None
    assert "반려" in notif.title


# ---------------------------------------------------------------------------
# merge_project (join)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_merge_project_happy_path(
    approval, boss_user, conflict_project, pending_project, staff_user
):
    project_pk = pending_project.pk
    merge_project(approval, admin_user=boss_user, merge_target=conflict_project)

    approval.refresh_from_db()
    assert approval.status == ProjectApproval.Status.JOINED
    # Pending project deleted
    assert not Project.objects.filter(pk=project_pk).exists()
    # Requester added to conflict project
    assert conflict_project.assigned_consultants.filter(pk=staff_user.pk).exists()


@pytest.mark.django_db
def test_merge_project_no_target_raises(approval, boss_user):
    """merge_project without conflict_project and no merge_target → raises."""
    with pytest.raises(InvalidApprovalTransition):
        merge_project(approval, admin_user=boss_user, merge_target=None)


# ---------------------------------------------------------------------------
# InvalidApprovalTransition — wrong state
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_approve_already_approved_raises(approval, boss_user):
    """Approving an already-approved approval raises InvalidApprovalTransition."""
    approve_project(approval, admin_user=boss_user)
    approval.refresh_from_db()

    with pytest.raises(InvalidApprovalTransition):
        approve_project(approval, admin_user=boss_user)


@pytest.mark.django_db
def test_reject_already_rejected_raises(approval, boss_user, pending_project):
    reject_project(approval, admin_user=boss_user)
    approval.refresh_from_db()

    with pytest.raises(InvalidApprovalTransition):
        reject_project(approval, admin_user=boss_user)


@pytest.mark.django_db
def test_invalid_transition_from_approved_to_joined(
    approval, boss_user, conflict_project
):
    """Cannot merge after already approved."""
    approve_project(approval, admin_user=boss_user)
    approval.refresh_from_db()

    with pytest.raises(InvalidApprovalTransition):
        merge_project(approval, admin_user=boss_user, merge_target=conflict_project)


# ---------------------------------------------------------------------------
# cancel_approval
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cancel_approval_deletes_project(approval, pending_project):
    project_pk = pending_project.pk
    cancel_approval(approval)

    assert not ProjectApproval.objects.filter(pk=approval.pk).exists()
    assert not Project.objects.filter(pk=project_pk).exists()


# ---------------------------------------------------------------------------
# send_admin_message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_admin_message_pending(approval, boss_user, staff_user):
    send_admin_message(approval, admin_user=boss_user, message="서류 보완 필요")

    approval.refresh_from_db()
    assert approval.admin_response == "서류 보완 필요"

    notif = Notification.objects.filter(recipient=staff_user).last()
    assert notif is not None
    assert "메시지" in notif.title


@pytest.mark.django_db
def test_send_admin_message_non_pending_raises(approval, boss_user):
    approve_project(approval, admin_user=boss_user)
    approval.refresh_from_db()

    with pytest.raises(InvalidApprovalTransition):
        send_admin_message(approval, admin_user=boss_user, message="이미 승인됨")
