import pytest

from projects.models import ProjectContext
from projects.services.context import (
    FORM_REGISTRY,
    discard_context,
    get_active_context,
    get_resume_url,
    save_context,
    validate_draft_data,
)


@pytest.mark.django_db
class TestValidateDraftData:
    def test_valid_data(self):
        assert validate_draft_data({"form": "contact_create", "fields": {}}) is True

    def test_missing_form_key(self):
        assert validate_draft_data({"fields": {}}) is False

    def test_not_a_dict(self):
        assert validate_draft_data("string") is False
        assert validate_draft_data(None) is False

    def test_oversized_data(self):
        huge = {"form": "test", "data": "x" * 60_000}
        assert validate_draft_data(huge) is False


@pytest.mark.django_db
class TestSaveContext:
    def test_create_new_context(self, project, user):
        ctx = save_context(
            project=project,
            user=user,
            last_step="contact_create",
            pending_action="홍길동 컨택 결과 입력",
            draft_data={"form": "contact_create", "fields": {"channel": "phone"}},
        )
        assert ctx.last_step == "contact_create"
        assert ctx.draft_data["fields"]["channel"] == "phone"

    def test_update_existing_context(self, project, user):
        save_context(
            project=project,
            user=user,
            last_step="contact_create",
            pending_action="first",
            draft_data={"form": "contact_create"},
        )
        ctx = save_context(
            project=project,
            user=user,
            last_step="submission_create",
            pending_action="second",
            draft_data={"form": "submission_create"},
        )
        assert ctx.last_step == "submission_create"
        assert (
            ProjectContext.objects.filter(project=project, consultant=user).count() == 1
        )


@pytest.mark.django_db
class TestGetActiveContext:
    def test_returns_context_when_exists(self, project, user):
        save_context(
            project=project,
            user=user,
            last_step="contact_create",
            pending_action="test",
            draft_data={"form": "contact_create"},
        )
        ctx = get_active_context(project, user)
        assert ctx is not None
        assert ctx.last_step == "contact_create"

    def test_returns_none_when_no_context(self, project, user):
        assert get_active_context(project, user) is None


@pytest.mark.django_db
class TestDiscardContext:
    def test_deletes_context(self, project, user):
        save_context(
            project=project,
            user=user,
            last_step="test",
            pending_action="test",
            draft_data={"form": "test"},
        )
        deleted = discard_context(project, user)
        assert deleted is True
        assert get_active_context(project, user) is None

    def test_returns_false_when_no_context(self, project, user):
        assert discard_context(project, user) is False


@pytest.mark.django_db
class TestGetResumeUrl:
    def test_known_form_returns_url(self, project, user):
        ctx = save_context(
            project=project,
            user=user,
            last_step="submission_create",
            pending_action="test",
            draft_data={"form": "submission_create"},
        )
        url = get_resume_url(ctx)
        assert url is not None
        assert f"/projects/{project.pk}/submissions/new/" in url
        assert f"resume={ctx.pk}" in url

    def test_unknown_form_returns_none(self, project, user):
        ctx = save_context(
            project=project,
            user=user,
            last_step="unknown_form",
            pending_action="test",
            draft_data={"form": "unknown_form"},
        )
        assert get_resume_url(ctx) is None


class TestFormRegistry:
    def test_registry_has_expected_keys(self):
        assert "submission_create" in FORM_REGISTRY
        assert "contact_create" not in FORM_REGISTRY  # removed in Phase 3b
