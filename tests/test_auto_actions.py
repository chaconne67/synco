import pytest
from django.db import IntegrityError

from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    ProjectContext,
)
from projects.services.auto_actions import (
    ConflictError,
    apply_action,
    dismiss_action,
    get_pending_actions,
)


@pytest.mark.django_db
class TestAutoActionModel:
    def test_create_auto_action(self, project):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="project_created",
            action_type=ActionType.POSTING_DRAFT,
            title="품질기획 공지 초안",
            data={"project_id": str(project.pk)},
        )
        assert action.status == ActionStatus.PENDING
        assert action.due_at is None
        assert action.created_by is None
        assert action.applied_by is None
        assert action.dismissed_by is None
        assert action.pk is not None

    def test_auto_action_status_choices(self):
        assert ActionStatus.PENDING == "pending"
        assert ActionStatus.APPLIED == "applied"
        assert ActionStatus.DISMISSED == "dismissed"

    def test_action_type_choices(self):
        assert ActionType.POSTING_DRAFT == "posting_draft"
        assert ActionType.CANDIDATE_SEARCH == "candidate_search"
        assert ActionType.SUBMISSION_DRAFT == "submission_draft"
        assert ActionType.OFFER_TEMPLATE == "offer_template"
        assert ActionType.FOLLOWUP_REMINDER == "followup_reminder"
        assert ActionType.RECONTACT_REMINDER == "recontact_reminder"


@pytest.mark.django_db
class TestProjectContextUniqueConstraint:
    def test_unique_context_per_project_consultant(self, project, user):
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="contact_create",
            draft_data={"form": "contact_create"},
        )
        with pytest.raises(IntegrityError):
            ProjectContext.objects.create(
                project=project,
                consultant=user,
                last_step="submission_create",
                draft_data={"form": "submission_create"},
            )

    def test_different_consultants_can_have_contexts(self, project, user, other_user):
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="contact_create",
            draft_data={"form": "contact_create"},
        )
        ctx2 = ProjectContext.objects.create(
            project=project,
            consultant=other_user,
            last_step="submission_create",
            draft_data={"form": "submission_create"},
        )
        assert ctx2.pk is not None


@pytest.mark.django_db
class TestGetPendingActions:
    def test_returns_pending_only(self, project, user):
        AutoAction.objects.create(
            project=project,
            trigger_event="project_created",
            action_type=ActionType.POSTING_DRAFT,
            title="Pending",
            data={},
        )
        AutoAction.objects.create(
            project=project,
            trigger_event="project_created",
            action_type=ActionType.CANDIDATE_SEARCH,
            title="Applied",
            data={},
            status=ActionStatus.APPLIED,
        )
        actions = get_pending_actions(project)
        assert len(actions) == 1
        assert actions[0].title == "Pending"


@pytest.mark.django_db
class TestApplyAction:
    def test_apply_pending_action(self, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test reminder",
            data={"submission_id": "fake-uuid", "message": "followup"},
        )
        apply_action(action.pk, user)
        action.refresh_from_db()
        assert action.status == ActionStatus.APPLIED
        assert action.applied_by == user

    def test_apply_already_applied_raises_conflict(self, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test",
            data={"submission_id": "fake-uuid"},
            status=ActionStatus.APPLIED,
        )
        with pytest.raises(ConflictError):
            apply_action(action.pk, user)

    def test_apply_dismissed_raises_conflict(self, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test",
            data={"submission_id": "fake-uuid"},
            status=ActionStatus.DISMISSED,
        )
        with pytest.raises(ConflictError):
            apply_action(action.pk, user)


@pytest.mark.django_db
class TestDismissAction:
    def test_dismiss_pending_action(self, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.POSTING_DRAFT,
            title="test",
            data={},
        )
        dismiss_action(action.pk, user)
        action.refresh_from_db()
        assert action.status == ActionStatus.DISMISSED
        assert action.dismissed_by == user

    def test_dismiss_already_applied_raises_conflict(self, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.POSTING_DRAFT,
            title="test",
            data={},
            status=ActionStatus.APPLIED,
        )
        with pytest.raises(ConflictError):
            dismiss_action(action.pk, user)
