# P16: Work Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add work continuity (autosave/resume of form state) and event-triggered auto-actions (posting drafts, candidate search, reminders) to the projects app.

**Architecture:** Two subsystems: (1) ProjectContext autosave/resume using a unique-per-consultant context row with three-tier JS save (periodic, sendBeacon, HTMX event), and (2) AutoAction model with Django signals creating lightweight pending records on model state transitions, plus a management command for time-based triggers. AI generation is lazy (on user demand), not in signals.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, PostgreSQL (UUID PKs, BaseModel), pytest-django

---

## File Structure

| File | Responsibility |
|------|---------------|
| `projects/models.py` | Add `AutoAction` model + `ActionType`/`ActionStatus` choices; add `UniqueConstraint` to `ProjectContext` |
| `projects/signals.py` (new) | `post_save` handlers for Project, Contact, Submission, Interview; create pending `AutoAction` records |
| `projects/apps.py` | Register signals in `ready()` |
| `projects/services/context.py` (new) | `FORM_REGISTRY`, `save_context()`, `get_active_context()`, `resume_context()`, `discard_context()`, `validate_draft_data()` |
| `projects/services/auto_actions.py` (new) | `apply_action()`, `dismiss_action()`, `validate_action_data()`, `get_pending_actions()` |
| `projects/views.py` | Add 7 views: context, context_save, context_resume, context_discard, auto_actions, auto_action_apply, auto_action_dismiss |
| `projects/urls.py` | Add 7 URL patterns |
| `projects/templates/projects/partials/context_banner.html` (new) | Context resume banner |
| `projects/templates/projects/partials/auto_actions_banner.html` (new) | Auto-actions pending banner |
| `static/js/context-autosave.js` (new) | Three-tier autosave JS |
| `projects/management/commands/check_due_actions.py` (new) | Cron command for lock expiry + due reminders |
| `tests/test_context.py` (new) | Tests for context save/resume/discard |
| `tests/test_auto_actions.py` (new) | Tests for auto-action creation, apply, dismiss, signals |
| `tests/test_check_due_actions.py` (new) | Tests for management command |
| `tests/conftest.py` (new) | Shared pytest fixtures |

---

### Task 1: Shared Test Fixtures

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create conftest with shared fixtures**

```python
# tests/conftest.py
import pytest
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization
from clients.models import Client
from projects.models import Project, ProjectStatus

User = get_user_model()


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def other_user(db, org):
    u = User.objects.create_user(username="consultant2", password="testpass123")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def other_org_user(db):
    other_org = Organization.objects.create(name="Other Org")
    u = User.objects.create_user(username="outsider", password="testpass123")
    Membership.objects.create(user=u, organization=other_org)
    return u


@pytest.fixture
def client_company(db, org):
    return Client.objects.create(name="Rayence", organization=org)


@pytest.fixture
def project(db, org, client_company, user):
    return Project.objects.create(
        client=client_company,
        organization=org,
        title="품질기획",
        status=ProjectStatus.NEW,
        created_by=user,
    )
```

- [ ] **Step 2: Verify fixtures load**

Run: `uv run pytest tests/conftest.py --collect-only`
Expected: No errors, fixtures discovered

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(p16): add shared pytest fixtures for projects tests"
```

---

### Task 2: AutoAction Model + ProjectContext UniqueConstraint

**Files:**
- Modify: `projects/models.py`

- [ ] **Step 1: Write the failing test for AutoAction model**

```python
# tests/test_auto_actions.py
import pytest
from django.db import IntegrityError

from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    ProjectContext,
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
        assert action.pk is not None  # UUID auto-generated

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auto_actions.py -v`
Expected: FAIL — `ActionType`, `ActionStatus`, `AutoAction` not importable

- [ ] **Step 3: Add model code to projects/models.py**

Add after the `MeetingRecord` class at the end of `projects/models.py`:

```python
class ActionType(models.TextChoices):
    POSTING_DRAFT = "posting_draft", "공지 초안"
    CANDIDATE_SEARCH = "candidate_search", "후보자 자동 서칭"
    SUBMISSION_DRAFT = "submission_draft", "제출 서류 초안"
    OFFER_TEMPLATE = "offer_template", "오퍼 템플릿"
    FOLLOWUP_REMINDER = "followup_reminder", "팔로업 리마인더"
    RECONTACT_REMINDER = "recontact_reminder", "재컨택 리마인더"


class ActionStatus(models.TextChoices):
    PENDING = "pending", "대기"
    APPLIED = "applied", "적용됨"
    DISMISSED = "dismissed", "무시됨"


class AutoAction(BaseModel):
    """이벤트 기반 자동 생성물."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="auto_actions",
    )
    trigger_event = models.CharField(max_length=100)
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    title = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ActionStatus.choices,
        default=ActionStatus.PENDING,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_auto_actions",
    )
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_auto_actions",
    )
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dismissed_auto_actions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AutoAction: {self.title} ({self.status})"
```

Also add `UniqueConstraint` to `ProjectContext.Meta`:

```python
class Meta:
    ordering = ["-updated_at"]
    constraints = [
        models.UniqueConstraint(
            fields=["project", "consultant"],
            name="unique_context_per_project_consultant",
        )
    ]
```

- [ ] **Step 4: Create and run migration**

Run: `uv run python manage.py makemigrations projects && uv run python manage.py migrate`
Expected: Migration created and applied successfully

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_auto_actions.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/models.py projects/migrations/ tests/test_auto_actions.py
git commit -m "feat(p16): add AutoAction model and ProjectContext unique constraint"
```

---

### Task 3: Context Service (save, get, resume, discard, validation)

**Files:**
- Create: `projects/services/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing tests for context service**

```python
# tests/test_context.py
import json

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
        assert ProjectContext.objects.filter(
            project=project, consultant=user
        ).count() == 1


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
            last_step="contact_create",
            pending_action="test",
            draft_data={"form": "contact_create"},
        )
        url = get_resume_url(ctx)
        assert url is not None
        assert f"/projects/{project.pk}/contacts/new/" in url
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
        assert "contact_create" in FORM_REGISTRY
        assert "submission_create" in FORM_REGISTRY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py -v`
Expected: FAIL — module `projects.services.context` not found

- [ ] **Step 3: Implement context service**

```python
# projects/services/context.py
"""ProjectContext CRUD + FORM_REGISTRY + resume/restore."""

from __future__ import annotations

import json
from typing import Any

from django.urls import reverse

from projects.models import ProjectContext


# --- Validation ---

REQUIRED_KEYS = {"form"}
MAX_DRAFT_SIZE = 50_000  # 50KB


def validate_draft_data(data: Any) -> bool:
    """Validate draft_data structure and size."""
    if not isinstance(data, dict):
        return False
    if not REQUIRED_KEYS.issubset(data.keys()):
        return False
    if len(json.dumps(data, ensure_ascii=False)) > MAX_DRAFT_SIZE:
        return False
    return True


# --- CRUD ---


def save_context(
    *,
    project,
    user,
    last_step: str,
    pending_action: str,
    draft_data: dict,
) -> ProjectContext:
    """Create or update context for this project+consultant pair."""
    ctx, _created = ProjectContext.objects.update_or_create(
        project=project,
        consultant=user,
        defaults={
            "last_step": last_step,
            "pending_action": pending_action,
            "draft_data": draft_data,
        },
    )
    return ctx


def get_active_context(project, user) -> ProjectContext | None:
    """Return the active context for this project+consultant, or None."""
    return ProjectContext.objects.filter(
        project=project,
        consultant=user,
    ).first()


def discard_context(project, user) -> bool:
    """Delete context for this project+consultant. Returns True if deleted."""
    count, _ = ProjectContext.objects.filter(
        project=project,
        consultant=user,
    ).delete()
    return count > 0


# --- Form Registry ---

FORM_REGISTRY: dict[str, dict[str, Any]] = {
    "contact_create": {
        "url_name": "projects:contact_create",
        "url_kwargs": lambda ctx: {"pk": str(ctx.project_id)},
    },
    "contact_update": {
        "url_name": "projects:contact_update",
        "url_kwargs": lambda ctx: {
            "pk": str(ctx.project_id),
            "contact_pk": ctx.draft_data.get("contact_id", ""),
        },
    },
    "submission_create": {
        "url_name": "projects:submission_create",
        "url_kwargs": lambda ctx: {"pk": str(ctx.project_id)},
    },
}


def get_resume_url(ctx: ProjectContext) -> str | None:
    """Build the resume redirect URL for this context, or None if unknown form."""
    form_name = ctx.draft_data.get("form", ctx.last_step)
    entry = FORM_REGISTRY.get(form_name)
    if not entry:
        return None
    base_url = reverse(entry["url_name"], kwargs=entry["url_kwargs"](ctx))
    return f"{base_url}?resume={ctx.pk}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_context.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/context.py tests/test_context.py
git commit -m "feat(p16): add context service with save, resume, discard, validation"
```

---

### Task 4: AutoAction Service (apply, dismiss, validation)

**Files:**
- Create: `projects/services/auto_actions.py`

- [ ] **Step 1: Write failing tests for auto_actions service**

Add to `tests/test_auto_actions.py`:

```python
from projects.models import ActionStatus, ActionType, AutoAction
from projects.services.auto_actions import (
    apply_action,
    dismiss_action,
    get_pending_actions,
    ConflictError,
)


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
        result = apply_action(action.pk, user)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auto_actions.py::TestGetPendingActions tests/test_auto_actions.py::TestApplyAction tests/test_auto_actions.py::TestDismissAction -v`
Expected: FAIL — module `projects.services.auto_actions` not found

- [ ] **Step 3: Implement auto_actions service**

```python
# projects/services/auto_actions.py
"""AutoAction management: create (idempotent), apply, dismiss, validate."""

from __future__ import annotations

import logging

from django.db import transaction

from projects.models import ActionStatus, ActionType, AutoAction

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when an action is not in the expected state."""

    pass


# --- Validation ---

ACTION_DATA_SCHEMA: dict[str, dict] = {
    ActionType.POSTING_DRAFT: {"required": [], "optional": ["text"]},
    ActionType.CANDIDATE_SEARCH: {"required": [], "optional": ["candidate_ids"]},
    ActionType.SUBMISSION_DRAFT: {"required": ["candidate_id"], "optional": ["draft_json"]},
    ActionType.OFFER_TEMPLATE: {"required": ["submission_id"], "optional": ["salary", "terms"]},
    ActionType.FOLLOWUP_REMINDER: {"required": ["submission_id"], "optional": ["message"]},
    ActionType.RECONTACT_REMINDER: {"required": ["contact_id"], "optional": ["message"]},
}


def validate_action_data(action_type: str, data: dict) -> bool:
    """Check that data has required keys for this action type."""
    schema = ACTION_DATA_SCHEMA.get(action_type)
    if not schema:
        return False
    for key in schema["required"]:
        if key not in data:
            return False
    return True


# --- Queries ---


def get_pending_actions(project) -> list[AutoAction]:
    """Return pending auto-actions for a project."""
    return list(
        AutoAction.objects.filter(
            project=project,
            status=ActionStatus.PENDING,
        ).order_by("-created_at")
    )


# --- Mutations ---


def apply_action(action_id, user) -> AutoAction:
    """Apply a pending action. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatus.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")
        action.status = ActionStatus.APPLIED
        action.applied_by = user
        action.save(update_fields=["status", "applied_by", "updated_at"])
    return action


def dismiss_action(action_id, user) -> AutoAction:
    """Dismiss a pending action. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatus.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")
        action.status = ActionStatus.DISMISSED
        action.dismissed_by = user
        action.save(update_fields=["status", "dismissed_by", "updated_at"])
    return action
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auto_actions.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/auto_actions.py tests/test_auto_actions.py
git commit -m "feat(p16): add auto_actions service with apply, dismiss, validation"
```

---

### Task 5: Django Signals for Event Triggers

**Files:**
- Create: `projects/signals.py`
- Modify: `projects/apps.py`

- [ ] **Step 1: Write failing tests for signals**

Add to `tests/test_auto_actions.py`:

```python
from candidates.models import Candidate
from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Interview,
    Project,
    ProjectStatus,
    Submission,
)


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
    def test_creates_submission_draft_action(self, project, user, org):
        candidate = Candidate.objects.create(
            name="홍길동", owned_by=org
        )
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

    def test_no_action_for_non_interested(self, project, user, org):
        candidate = Candidate.objects.create(
            name="김영희", owned_by=org
        )
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.NO_RESPONSE,
        )
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.SUBMISSION_DRAFT,
        ).count() == 0

    def test_idempotent_on_resave(self, project, user, org):
        candidate = Candidate.objects.create(
            name="이철수", owned_by=org
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.INTERESTED,
        )
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.SUBMISSION_DRAFT,
        ).count() == 1
        contact.notes = "Updated notes"
        contact.save()
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.SUBMISSION_DRAFT,
        ).count() == 1


@pytest.mark.django_db
class TestInterviewPassedSignal:
    def test_creates_offer_template_action(self, project, user, org):
        candidate = Candidate.objects.create(
            name="박지성", owned_by=org
        )
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

    def test_no_action_for_non_passed(self, project, user, org):
        candidate = Candidate.objects.create(
            name="최민수", owned_by=org
        )
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
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.OFFER_TEMPLATE,
        ).count() == 0


@pytest.mark.django_db
class TestSubmissionSubmittedSignal:
    def test_creates_followup_reminder(self, project, user, org):
        candidate = Candidate.objects.create(
            name="강감찬", owned_by=org
        )
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auto_actions.py::TestProjectCreatedSignal -v`
Expected: FAIL — signals not registered, no AutoActions created

- [ ] **Step 3: Create signals.py**

```python
# projects/signals.py
"""Event trigger signal handlers — create lightweight AutoAction records."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Interview,
    Project,
    ProjectStatus,
    Submission,
)


@receiver(post_save, sender=Project)
def on_project_created(sender, instance, created, **kwargs):
    """New project → pending posting draft + candidate search actions."""
    if not created or instance.status != ProjectStatus.NEW:
        return
    transaction.on_commit(lambda: _create_project_actions(instance))


def _create_project_actions(project):
    for action_type, title in [
        (ActionType.POSTING_DRAFT, f"{project.title} 공지 초안"),
        (ActionType.CANDIDATE_SEARCH, f"{project.title} 후보자 자동 서칭"),
    ]:
        AutoAction.objects.get_or_create(
            project=project,
            action_type=action_type,
            status=ActionStatus.PENDING,
            defaults={
                "trigger_event": "project_created",
                "title": title,
                "data": {"project_id": str(project.pk)},
            },
        )


@receiver(post_save, sender=Contact)
def on_contact_result(sender, instance, **kwargs):
    """Contact with INTERESTED result → pending submission draft action."""
    if instance.result != Contact.Result.INTERESTED:
        return
    candidate_id = str(instance.candidate_id)
    if AutoAction.objects.filter(
        project=instance.project,
        action_type=ActionType.SUBMISSION_DRAFT,
        status=ActionStatus.PENDING,
        data__candidate_id=candidate_id,
    ).exists():
        return
    transaction.on_commit(
        lambda: AutoAction.objects.create(
            project=instance.project,
            trigger_event="contact_interested",
            action_type=ActionType.SUBMISSION_DRAFT,
            title=f"{instance.candidate.name} 제출 서류 초안",
            data={"candidate_id": candidate_id},
        )
    )


@receiver(post_save, sender=Submission)
def on_submission_submitted(sender, instance, **kwargs):
    """Submission status=SUBMITTED → followup reminder with due_at +3 days."""
    if instance.status != Submission.Status.SUBMITTED:
        return
    submission_id = str(instance.pk)
    if AutoAction.objects.filter(
        project=instance.project,
        action_type=ActionType.FOLLOWUP_REMINDER,
        status=ActionStatus.PENDING,
        data__submission_id=submission_id,
    ).exists():
        return
    due = timezone.now() + timedelta(days=3)
    transaction.on_commit(
        lambda: AutoAction.objects.create(
            project=instance.project,
            trigger_event="submission_submitted",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title=f"{instance.candidate.name} 팔로업 리마인더",
            data={"submission_id": submission_id},
            due_at=due,
        )
    )


@receiver(post_save, sender=Interview)
def on_interview_passed(sender, instance, **kwargs):
    """Interview result=PASSED → pending offer template action."""
    if instance.result != Interview.Result.PASSED:
        return
    submission_id = str(instance.submission_id)
    if AutoAction.objects.filter(
        project=instance.submission.project,
        action_type=ActionType.OFFER_TEMPLATE,
        status=ActionStatus.PENDING,
        data__submission_id=submission_id,
    ).exists():
        return
    transaction.on_commit(
        lambda: AutoAction.objects.create(
            project=instance.submission.project,
            trigger_event="interview_passed",
            action_type=ActionType.OFFER_TEMPLATE,
            title=f"{instance.submission.candidate.name} 오퍼 템플릿",
            data={"submission_id": submission_id},
        )
    )
```

- [ ] **Step 4: Register signals in apps.py**

Replace `projects/apps.py`:

```python
from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projects"

    def ready(self):
        import projects.signals  # noqa: F401
```

- [ ] **Step 5: Run all signal tests**

Run: `uv run pytest tests/test_auto_actions.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/signals.py projects/apps.py tests/test_auto_actions.py
git commit -m "feat(p16): add event trigger signals for auto-action creation"
```

---

### Task 6: Views + URLs (context + auto-actions endpoints)

**Files:**
- Modify: `projects/views.py`
- Modify: `projects/urls.py`

- [ ] **Step 1: Write failing tests for views**

Create `tests/test_context_views.py`:

```python
# tests/test_context_views.py
import json

import pytest
from django.test import Client as TestClient

from projects.models import ActionStatus, ActionType, AutoAction, ProjectContext


@pytest.fixture
def auth_client(user):
    client = TestClient()
    client.force_login(user)
    return client


@pytest.fixture
def other_org_client(other_org_user):
    client = TestClient()
    client.force_login(other_org_user)
    return client


@pytest.mark.django_db
class TestContextSaveView:
    def test_save_creates_context(self, auth_client, project, user):
        url = f"/projects/{project.pk}/context/save/"
        data = {
            "last_step": "contact_create",
            "pending_action": "Test action",
            "draft_data": {"form": "contact_create", "fields": {}},
        }
        response = auth_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 204
        ctx = ProjectContext.objects.get(project=project, consultant=user)
        assert ctx.last_step == "contact_create"

    def test_save_invalid_data_returns_400(self, auth_client, project):
        url = f"/projects/{project.pk}/context/save/"
        data = {
            "last_step": "test",
            "pending_action": "test",
            "draft_data": {"no_form_key": True},
        }
        response = auth_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_save_forbidden_for_other_org(self, other_org_client, project):
        url = f"/projects/{project.pk}/context/save/"
        data = {
            "last_step": "test",
            "pending_action": "test",
            "draft_data": {"form": "test"},
        }
        response = other_org_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestContextDiscardView:
    def test_discard_deletes_context(self, auth_client, project, user):
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="test",
            draft_data={"form": "test"},
        )
        url = f"/projects/{project.pk}/context/discard/"
        response = auth_client.post(url)
        assert response.status_code == 200
        assert not ProjectContext.objects.filter(
            project=project, consultant=user
        ).exists()


@pytest.mark.django_db
class TestAutoActionApplyView:
    def test_apply_action(self, auth_client, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test",
            data={"submission_id": "fake", "message": "test"},
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/apply/"
        response = auth_client.post(url)
        assert response.status_code == 200
        action.refresh_from_db()
        assert action.status == ActionStatus.APPLIED

    def test_apply_already_applied_returns_409(self, auth_client, project):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test",
            data={"submission_id": "fake"},
            status=ActionStatus.APPLIED,
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/apply/"
        response = auth_client.post(url)
        assert response.status_code == 409


@pytest.mark.django_db
class TestAutoActionDismissView:
    def test_dismiss_action(self, auth_client, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.POSTING_DRAFT,
            title="test",
            data={},
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/dismiss/"
        response = auth_client.post(url)
        assert response.status_code == 200
        action.refresh_from_db()
        assert action.status == ActionStatus.DISMISSED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context_views.py -v`
Expected: FAIL — 404 (URLs not registered)

- [ ] **Step 3: Add views to projects/views.py**

Add at the end of `projects/views.py`:

```python
# --- P16: Work Continuity ---

from projects.services.context import (
    discard_context,
    get_active_context,
    get_resume_url,
    save_context,
    validate_draft_data,
)
from projects.services.auto_actions import (
    apply_action,
    dismiss_action,
    get_pending_actions,
    ConflictError,
)
from .models import AutoAction, ProjectContext


@login_required
@require_http_methods(["GET"])
def project_context(request, pk):
    """GET: Return active context banner partial."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    ctx = get_active_context(project, request.user)
    return render(request, "projects/partials/context_banner.html", {
        "project": project,
        "context": ctx,
        "resume_url": get_resume_url(ctx) if ctx else None,
    })


@login_required
@require_http_methods(["POST"])
def project_context_save(request, pk):
    """POST: Save/update context (autosave endpoint)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # Accept both JSON and form-encoded (sendBeacon)
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse(status=400)
    else:
        # sendBeacon sends application/x-www-form-urlencoded
        raw = request.POST.get("data", request.body.decode("utf-8", errors="replace"))
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse(status=400)

    last_step = body.get("last_step", "")
    pending_action = body.get("pending_action", "")
    draft_data = body.get("draft_data", {})

    if not validate_draft_data(draft_data):
        return HttpResponse(status=400)

    save_context(
        project=project,
        user=request.user,
        last_step=last_step,
        pending_action=pending_action,
        draft_data=draft_data,
    )
    return HttpResponse(status=204)


@login_required
@require_http_methods(["POST"])
def project_context_resume(request, pk):
    """POST: Resume from context → redirect to target form."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    ctx = get_active_context(project, request.user)
    if not ctx:
        return HttpResponse(status=404)
    resume_url = get_resume_url(ctx)
    if not resume_url:
        return HttpResponse(status=404)
    response = HttpResponse(status=200)
    response["HX-Redirect"] = resume_url
    return response


@login_required
@require_http_methods(["POST"])
def project_context_discard(request, pk):
    """POST: Discard the active context."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    discard_context(project, request.user)
    return render(request, "projects/partials/context_banner.html", {
        "project": project,
        "context": None,
        "resume_url": None,
    })


@login_required
@require_http_methods(["GET"])
def project_auto_actions(request, pk):
    """GET: List pending auto-actions."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    actions = get_pending_actions(project)
    return render(request, "projects/partials/auto_actions_banner.html", {
        "project": project,
        "actions": actions,
    })


@login_required
@require_http_methods(["POST"])
def auto_action_apply(request, pk, action_pk):
    """POST: Apply an auto-action."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    action = get_object_or_404(AutoAction, pk=action_pk, project=project)
    try:
        apply_action(action.pk, request.user)
    except ConflictError:
        return HttpResponse("이미 처리된 액션입니다.", status=409)
    actions = get_pending_actions(project)
    return render(request, "projects/partials/auto_actions_banner.html", {
        "project": project,
        "actions": actions,
    })


@login_required
@require_http_methods(["POST"])
def auto_action_dismiss(request, pk, action_pk):
    """POST: Dismiss an auto-action."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    action = get_object_or_404(AutoAction, pk=action_pk, project=project)
    try:
        dismiss_action(action.pk, request.user)
    except ConflictError:
        return HttpResponse("이미 처리된 액션입니다.", status=409)
    actions = get_pending_actions(project)
    return render(request, "projects/partials/auto_actions_banner.html", {
        "project": project,
        "actions": actions,
    })
```

- [ ] **Step 4: Add URL patterns to projects/urls.py**

Add before the closing `]` in `urlpatterns`:

```python
    # P16: Work Continuity
    path(
        "<uuid:pk>/context/",
        views.project_context,
        name="project_context",
    ),
    path(
        "<uuid:pk>/context/save/",
        views.project_context_save,
        name="project_context_save",
    ),
    path(
        "<uuid:pk>/context/resume/",
        views.project_context_resume,
        name="project_context_resume",
    ),
    path(
        "<uuid:pk>/context/discard/",
        views.project_context_discard,
        name="project_context_discard",
    ),
    path(
        "<uuid:pk>/auto-actions/",
        views.project_auto_actions,
        name="project_auto_actions",
    ),
    path(
        "<uuid:pk>/auto-actions/<uuid:action_pk>/apply/",
        views.auto_action_apply,
        name="auto_action_apply",
    ),
    path(
        "<uuid:pk>/auto-actions/<uuid:action_pk>/dismiss/",
        views.auto_action_dismiss,
        name="auto_action_dismiss",
    ),
```

- [ ] **Step 5: Create template stubs**

Create `projects/templates/projects/partials/context_banner.html`:

```html
{% if context %}
<div id="context-banner" class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
  <div class="flex items-start justify-between">
    <div>
      <h3 class="text-[14px] font-semibold text-amber-800">중단된 작업</h3>
      <p class="text-[13px] text-amber-700 mt-1">{{ context.pending_action }}</p>
      <p class="text-[12px] text-amber-500 mt-0.5">{{ context.updated_at|timesince }} 전 중단</p>
    </div>
    <div class="flex items-center gap-2">
      {% if resume_url %}
      <button hx-post="{% url 'projects:project_context_resume' project.pk %}"
              class="px-3 py-1.5 bg-amber-600 text-white text-[13px] rounded-lg hover:bg-amber-700 transition">
        이어서 하기
      </button>
      {% endif %}
      <button hx-post="{% url 'projects:project_context_discard' project.pk %}"
              hx-target="#context-banner-wrapper"
              hx-swap="innerHTML"
              class="px-3 py-1.5 bg-white text-amber-700 text-[13px] border border-amber-300 rounded-lg hover:bg-amber-50 transition">
        취소
      </button>
    </div>
  </div>
</div>
{% endif %}
```

Create `projects/templates/projects/partials/auto_actions_banner.html`:

```html
{% if actions %}
<div id="auto-actions-banner" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
  <h3 class="text-[14px] font-semibold text-blue-800 mb-3">자동 생성 ({{ actions|length }}건)</h3>
  <div class="space-y-2">
    {% for action in actions %}
    <div class="flex items-center justify-between">
      <span class="text-[13px] text-blue-700">{{ action.title }}</span>
      <div class="flex items-center gap-2">
        <button hx-post="{% url 'projects:auto_action_apply' project.pk action.pk %}"
                hx-target="#auto-actions-wrapper"
                hx-swap="innerHTML"
                class="px-2.5 py-1 bg-blue-600 text-white text-[12px] rounded-lg hover:bg-blue-700 transition">
          확인
        </button>
        <button hx-post="{% url 'projects:auto_action_dismiss' project.pk action.pk %}"
                hx-target="#auto-actions-wrapper"
                hx-swap="innerHTML"
                class="px-2.5 py-1 bg-white text-blue-600 text-[12px] border border-blue-300 rounded-lg hover:bg-blue-50 transition">
          무시
        </button>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 6: Run view tests**

Run: `uv run pytest tests/test_context_views.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add projects/views.py projects/urls.py tests/test_context_views.py \
  projects/templates/projects/partials/context_banner.html \
  projects/templates/projects/partials/auto_actions_banner.html
git commit -m "feat(p16): add context and auto-action views, URLs, and templates"
```

---

### Task 7: Management Command (check_due_actions)

**Files:**
- Create: `projects/management/commands/check_due_actions.py`
- Create: `tests/test_check_due_actions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_check_due_actions.py
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from candidates.models import Candidate
from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Notification,
)


@pytest.mark.django_db
class TestCheckDueActions:
    def test_creates_recontact_reminder_for_expiring_lock(self, project, user, org):
        candidate = Candidate.objects.create(name="만료임박", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(hours=20),
        )
        call_command("check_due_actions")
        actions = AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        )
        assert actions.count() == 1
        assert "만료임박" in actions[0].title

    def test_ignores_already_expired_locks(self, project, user, org):
        candidate = Candidate.objects.create(name="이미만료", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() - timedelta(hours=1),
        )
        call_command("check_due_actions")
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        ).count() == 0

    def test_ignores_far_future_locks(self, project, user, org):
        candidate = Candidate.objects.create(name="먼미래", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(days=5),
        )
        call_command("check_due_actions")
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        ).count() == 0

    def test_idempotent_run(self, project, user, org):
        candidate = Candidate.objects.create(name="멱등", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(hours=20),
        )
        call_command("check_due_actions")
        call_command("check_due_actions")
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        ).count() == 1

    def test_processes_due_followup_reminders(self, project, user, org):
        """Due followup reminders create Notification records."""
        candidate = Candidate.objects.create(name="팔로업", owned_by=org)
        AutoAction.objects.create(
            project=project,
            trigger_event="submission_submitted",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="팔로업 리마인더",
            data={"submission_id": "fake-uuid", "message": "팔로업 필요"},
            due_at=timezone.now() - timedelta(hours=1),
            created_by=user,
        )
        call_command("check_due_actions")
        notifs = Notification.objects.filter(
            type=Notification.Type.REMINDER,
        )
        assert notifs.count() >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_check_due_actions.py -v`
Expected: FAIL — command not found

- [ ] **Step 3: Implement management command**

```python
# projects/management/commands/check_due_actions.py
"""Check for due auto-actions and expiring locks. Run daily via cron."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Notification,
)


class Command(BaseCommand):
    help = "Check for expiring locks and process due auto-action reminders"

    def handle(self, *args, **options):
        now = timezone.now()
        tomorrow = now + timedelta(days=1)

        lock_count = self._check_expiring_locks(now, tomorrow)
        due_count = self._process_due_actions(now)

        self.stdout.write(
            f"check_due_actions: {lock_count} lock reminders, "
            f"{due_count} due actions processed"
        )

    def _check_expiring_locks(self, now, tomorrow) -> int:
        """Create recontact reminders for locks expiring within 24h."""
        expiring = Contact.objects.filter(
            result=Contact.Result.RESERVED,
            locked_until__lte=tomorrow,
            locked_until__gt=now,
        ).select_related("candidate", "project", "consultant")

        count = 0
        for contact in expiring:
            _, created = AutoAction.objects.get_or_create(
                project=contact.project,
                action_type=ActionType.RECONTACT_REMINDER,
                status=ActionStatus.PENDING,
                data__contact_id=str(contact.pk),
                defaults={
                    "trigger_event": "lock_expiring",
                    "title": f"{contact.candidate.name} 컨택 잠금 내일 만료",
                    "data": {"contact_id": str(contact.pk)},
                    "created_by": contact.consultant,
                },
            )
            if created:
                count += 1
        return count

    def _process_due_actions(self, now) -> int:
        """Create Notifications for due pending actions."""
        due_actions = AutoAction.objects.filter(
            status=ActionStatus.PENDING,
            due_at__lte=now,
        ).select_related("project", "created_by")

        count = 0
        for action in due_actions:
            # Find the consultant to notify
            recipient = action.created_by
            if not recipient:
                # Fallback: project creator
                recipient = action.project.created_by
            if not recipient:
                continue

            # Create notification (idempotent by checking existing)
            _, created = Notification.objects.get_or_create(
                recipient=recipient,
                type=Notification.Type.REMINDER,
                title=action.title,
                defaults={
                    "body": action.data.get("message", action.title),
                },
            )
            if created:
                count += 1
        return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_check_due_actions.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/management/commands/check_due_actions.py tests/test_check_due_actions.py
git commit -m "feat(p16): add check_due_actions management command for cron"
```

---

### Task 8: Autosave JavaScript

**Files:**
- Create: `static/js/context-autosave.js`

- [ ] **Step 1: Create three-tier autosave script**

```javascript
// static/js/context-autosave.js
// Three-tier autosave: periodic (primary) + sendBeacon (unload) + HTMX event (in-app nav)

(function () {
  "use strict";

  const AUTOSAVE_INTERVAL_MS = 30000; // 30 seconds
  let _timer = null;
  let _dirty = false;
  let _lastSaved = null;

  function getAutosaveForms() {
    return document.querySelectorAll("form[data-autosave]");
  }

  function getProjectPk() {
    const el = document.querySelector("[data-project-pk]");
    return el ? el.dataset.projectPk : null;
  }

  function getFormName() {
    const form = document.querySelector("form[data-autosave]");
    return form ? form.dataset.autosave : null;
  }

  function collectFormData(form) {
    const formData = new FormData(form);
    const fields = {};
    for (const [key, value] of formData.entries()) {
      if (key === "csrfmiddlewaretoken") continue;
      fields[key] = value;
    }
    return fields;
  }

  function buildPayload() {
    const form = document.querySelector("form[data-autosave]");
    if (!form) return null;
    const formName = getFormName();
    const fields = collectFormData(form);
    return {
      last_step: formName,
      pending_action: form.dataset.autosaveAction || "",
      draft_data: {
        form: formName,
        fields: fields,
      },
    };
  }

  function getSaveUrl() {
    const pk = getProjectPk();
    if (!pk) return null;
    return `/projects/${pk}/context/save/`;
  }

  function getCsrfToken() {
    const cookie = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="));
    return cookie ? cookie.split("=")[1] : "";
  }

  // Tier 1: Periodic save via fetch
  function periodicSave() {
    if (!_dirty) return;
    const url = getSaveUrl();
    const payload = buildPayload();
    if (!url || !payload) return;

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(() => {
        _dirty = false;
        _lastSaved = Date.now();
      })
      .catch(() => {
        /* silent fail — will retry next interval */
      });
  }

  // Tier 2: sendBeacon on unload
  function beaconSave() {
    if (!_dirty) return;
    const url = getSaveUrl();
    const payload = buildPayload();
    if (!url || !payload) return;

    const blob = new Blob([JSON.stringify(payload)], {
      type: "application/json",
    });
    navigator.sendBeacon(url, blob);
  }

  // Tier 3: HTMX in-app navigation
  function htmxSave() {
    if (!_dirty) return;
    periodicSave();
  }

  function markDirty() {
    _dirty = true;
  }

  function init() {
    const forms = getAutosaveForms();
    if (forms.length === 0) return;

    // Listen for input changes
    forms.forEach((form) => {
      form.addEventListener("input", markDirty);
      form.addEventListener("change", markDirty);
    });

    // Tier 1: periodic
    _timer = setInterval(periodicSave, AUTOSAVE_INTERVAL_MS);

    // Tier 2: unload
    window.addEventListener("beforeunload", beaconSave);

    // Tier 3: HTMX navigation
    document.addEventListener("htmx:beforeHistorySave", htmxSave);
  }

  function cleanup() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    window.removeEventListener("beforeunload", beaconSave);
    document.removeEventListener("htmx:beforeHistorySave", htmxSave);
  }

  // Re-initialize after HTMX swaps
  document.addEventListener("htmx:afterSettle", function () {
    cleanup();
    init();
  });

  // Initial setup
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

- [ ] **Step 2: Verify file exists and is valid JS**

Run: `ls -la /home/work/synco/static/js/context-autosave.js && echo "OK"`
Expected: File listed, "OK"

- [ ] **Step 3: Commit**

```bash
git add static/js/context-autosave.js
git commit -m "feat(p16): add three-tier autosave JavaScript"
```

---

### Task 9: Integrate Banners into Overview Tab

**Files:**
- Modify: `projects/templates/projects/partials/tab_overview.html`
- Modify: `projects/views.py` (project_tab_overview view to pass context)

- [ ] **Step 1: Find and read the tab_overview view**

Read `projects/views.py` to find the `project_tab_overview` view and understand what context it passes.

- [ ] **Step 2: Modify the view to include context and auto-actions**

In the `project_tab_overview` view, add:

```python
from projects.services.context import get_active_context, get_resume_url
from projects.services.auto_actions import get_pending_actions

# Inside project_tab_overview:
ctx = get_active_context(project, request.user)
pending_actions = get_pending_actions(project)

# Add to template context dict:
# "context": ctx,
# "resume_url": get_resume_url(ctx) if ctx else None,
# "pending_actions": pending_actions,
```

- [ ] **Step 3: Add banner includes to tab_overview.html**

At the top of `tab_overview.html`, before the first `<section>`:

```html
<!-- P16: Context resume banner -->
<div id="context-banner-wrapper">
  {% include "projects/partials/context_banner.html" %}
</div>

<!-- P16: Auto-actions banner -->
<div id="auto-actions-wrapper">
  {% include "projects/partials/auto_actions_banner.html" with actions=pending_actions %}
</div>
```

- [ ] **Step 4: Run full test suite to check nothing breaks**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/templates/projects/partials/tab_overview.html
git commit -m "feat(p16): integrate context and auto-action banners into overview tab"
```

---

### Task 10: Lint + Final Verification

- [ ] **Step 1: Run ruff format and lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: No errors remaining

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Run migration check**

Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 4: Fix any issues found**

If there are lint errors or test failures, fix them.

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "style(p16): apply ruff formatting and fix lint issues"
```
