import pytest
from django.db import IntegrityError

from candidates.models import Candidate
from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Interview,
    Project,
    ProjectContext,
    ProjectStatus,
    Submission,
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


@pytest.mark.django_db
class TestProjectCreatedSignal:
    def test_creates_posting_and_search_actions(self, org, client_company, user):
        """Creating a NEW project triggers 2 AutoActions."""
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Signal Test",
            status=ProjectStatus.NEW,
            created_by=user,
        )
        actions = AutoAction.objects.filter(project=project)
        assert actions.count() == 2
        types = set(actions.values_list("action_type", flat=True))
        assert types == {ActionType.POSTING_DRAFT, ActionType.CANDIDATE_SEARCH}
        for action in actions:
            assert action.status == ActionStatus.PENDING
            assert action.trigger_event == "project_created"

    def test_no_actions_for_non_new_status(self, org, client_company, user):
        """Projects created with non-NEW status don't trigger actions."""
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="On Hold",
            status=ProjectStatus.ON_HOLD,
            created_by=user,
        )
        assert AutoAction.objects.filter(project=project).count() == 0

    def test_idempotent_on_resave(self, org, client_company, user):
        """Re-saving a project doesn't create duplicate actions."""
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Idempotent Test",
            status=ProjectStatus.NEW,
            created_by=user,
        )
        assert AutoAction.objects.filter(project=project).count() == 2
        project.title = "Updated"
        project.save()
        assert AutoAction.objects.filter(project=project).count() == 2


@pytest.mark.django_db
class TestContactInterestedSignal:
    def test_creates_submission_draft_action(self, org, client_company, user):
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Contact Test",
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )
        candidate = Candidate.objects.create(name="홍길동", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.INTERESTED,
        )
        actions = AutoAction.objects.filter(
            project=project,
            action_type=ActionType.SUBMISSION_DRAFT,
        )
        assert actions.count() == 1
        assert str(candidate.pk) in actions[0].data.get("candidate_id", "")

    def test_no_action_for_non_interested(self, org, client_company, user):
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Contact Test 2",
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )
        candidate = Candidate.objects.create(name="김영희", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.NO_RESPONSE,
        )
        assert (
            AutoAction.objects.filter(
                project=project,
                action_type=ActionType.SUBMISSION_DRAFT,
            ).count()
            == 0
        )

    def test_idempotent_on_resave(self, org, client_company, user):
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Contact Test 3",
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )
        candidate = Candidate.objects.create(name="이철수", owned_by=org)
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.INTERESTED,
        )
        assert (
            AutoAction.objects.filter(
                project=project,
                action_type=ActionType.SUBMISSION_DRAFT,
            ).count()
            == 1
        )
        contact.notes = "Updated notes"
        contact.save()
        assert (
            AutoAction.objects.filter(
                project=project,
                action_type=ActionType.SUBMISSION_DRAFT,
            ).count()
            == 1
        )


@pytest.mark.django_db
class TestInterviewPassedSignal:
    def test_creates_offer_template_action(self, org, client_company, user):
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Interview Test",
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )
        candidate = Candidate.objects.create(name="박지성", owned_by=org)
        submission = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
        )
        from django.utils import timezone

        Interview.objects.create(
            submission=submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.PASSED,
        )
        actions = AutoAction.objects.filter(
            project=project,
            action_type=ActionType.OFFER_TEMPLATE,
        )
        assert actions.count() == 1

    def test_no_action_for_non_passed(self, org, client_company, user):
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Interview Test 2",
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )
        candidate = Candidate.objects.create(name="최민수", owned_by=org)
        submission = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
        )
        from django.utils import timezone

        Interview.objects.create(
            submission=submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.PENDING,
        )
        assert (
            AutoAction.objects.filter(
                project=project,
                action_type=ActionType.OFFER_TEMPLATE,
            ).count()
            == 0
        )


@pytest.mark.django_db
class TestSubmissionSubmittedSignal:
    def test_creates_followup_reminder(self, org, client_company, user):
        project = Project.objects.create(
            client=client_company,
            organization=org,
            title="Submission Test",
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )
        candidate = Candidate.objects.create(name="강감찬", owned_by=org)
        submission = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            status=Submission.Status.SUBMITTED,
        )
        actions = AutoAction.objects.filter(
            project=project,
            action_type=ActionType.FOLLOWUP_REMINDER,
        )
        assert actions.count() == 1
        assert actions[0].due_at is not None
