# P11: Project Collision & Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement collision detection on project creation and admin approval workflow so duplicate projects within the same client are reviewed before activation.

**Architecture:** Extend the existing `ProjectApproval` skeleton model with `conflict_score` and `conflict_type` fields. Add a `collision.py` service for title similarity matching and an `approval.py` service for state-transition logic. Modify `project_create` to detect collisions and route to approval flow. Add OWNER-only approval queue views under `/projects/approvals/`.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Tailwind CSS

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `projects/models.py` | Modify | Add `ConflictType` choices, `conflict_score`/`conflict_type` fields to `ProjectApproval` |
| `projects/migrations/0007_p11_approval_collision_fields.py` | Create | Migration for new fields |
| `projects/services/collision.py` | Create | Title similarity scoring, collision detection |
| `projects/services/approval.py` | Create | Approval state transitions, decide logic |
| `projects/forms.py` | Modify | Remove `status` from `ProjectForm`, add `ApprovalDecisionForm` |
| `projects/views.py` | Modify | Add collision check, approval queue, approval decide, cancel views; add pending_approval guards |
| `projects/urls.py` | Modify | Add collision/approval URLs |
| `projects/admin.py` | Modify | Add `conflict_score`, `conflict_type` to `ProjectApprovalAdmin` |
| `projects/templates/projects/partials/collision_warning.html` | Create | HTMX partial for collision detection results |
| `projects/templates/projects/project_form.html` | Modify | Add collision check HTMX + JS triggers |
| `projects/templates/projects/approval_queue.html` | Create | Admin approval queue page |
| `projects/templates/projects/partials/approval_card.html` | Create | Single approval request card partial |
| `tests/test_p11_collision_approval.py` | Create | Full test suite |

---

### Task 1: Model — Add collision fields to ProjectApproval

**Files:**
- Modify: `projects/models.py:365-411`
- Create: `projects/migrations/0007_p11_approval_collision_fields.py`
- Modify: `projects/admin.py:55-59`
- Test: `tests/test_p11_collision_approval.py`

- [ ] **Step 1: Write the failing test for new fields**

```python
# tests/test_p11_collision_approval.py
"""P11: Collision detection and approval workflow tests."""

import pytest
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Project, ProjectApproval, ProjectStatus


# --- Fixtures ---

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_owner(db, org):
    user = User.objects.create_user(username="owner", password="test1234")
    Membership.objects.create(user=user, organization=org, role="owner")
    return user


@pytest.fixture
def user_consultant(db, org):
    user = User.objects.create_user(username="consultant", password="test1234")
    Membership.objects.create(user=user, organization=org, role="consultant")
    return user


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT", organization=org)


@pytest.fixture
def existing_project(org, client_obj, user_consultant):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="품질기획팀장",
        status="searching",
        created_by=user_consultant,
    )


@pytest.fixture
def auth_owner(user_owner):
    c = TestClient()
    c.login(username="owner", password="test1234")
    return c


@pytest.fixture
def auth_consultant(user_consultant):
    c = TestClient()
    c.login(username="consultant", password="test1234")
    return c


# --- Task 1: Model tests ---

class TestProjectApprovalModel:
    @pytest.mark.django_db
    def test_conflict_score_field_exists(self, org, client_obj, user_consultant, existing_project):
        approval = ProjectApproval.objects.create(
            project=existing_project,
            requested_by=user_consultant,
            conflict_score=0.85,
            conflict_type="높은중복",
        )
        approval.refresh_from_db()
        assert approval.conflict_score == 0.85
        assert approval.conflict_type == "높은중복"

    @pytest.mark.django_db
    def test_conflict_score_default(self, org, client_obj, user_consultant, existing_project):
        approval = ProjectApproval.objects.create(
            project=existing_project,
            requested_by=user_consultant,
        )
        approval.refresh_from_db()
        assert approval.conflict_score == 0.0
        assert approval.conflict_type == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestProjectApprovalModel -v`
Expected: FAIL — `conflict_score` and `conflict_type` don't exist on model yet

- [ ] **Step 3: Add ConflictType choices and fields to ProjectApproval**

In `projects/models.py`, add `ConflictType` above `ProjectApproval` class and add fields:

```python
class ConflictType(models.TextChoices):
    HIGH = "높은중복", "높은 중복 가능성"
    MEDIUM = "참고정보", "참고 정보"
```

Add to the `ProjectApproval` class, after `conflict_project`:

```python
    conflict_score = models.FloatField(default=0.0)
    conflict_type = models.CharField(
        max_length=20,
        choices=ConflictType.choices,
        blank=True,
        default="",
    )
```

- [ ] **Step 4: Generate and apply migration**

Run:
```bash
uv run python manage.py makemigrations projects --name p11_approval_collision_fields
uv run python manage.py migrate
```

- [ ] **Step 5: Update admin.py**

In `projects/admin.py`, update `ProjectApprovalAdmin`:

```python
@admin.register(ProjectApproval)
class ProjectApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "requested_by",
        "conflict_type",
        "conflict_score",
        "status",
        "decided_by",
        "decided_at",
    )
    list_filter = ("status", "conflict_type")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestProjectApprovalModel -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add projects/models.py projects/migrations/0007_p11_approval_collision_fields.py projects/admin.py tests/test_p11_collision_approval.py
git commit -m "feat(p11): add conflict_score and conflict_type fields to ProjectApproval"
```

---

### Task 2: Service — Collision detection

**Files:**
- Create: `projects/services/collision.py`
- Test: `tests/test_p11_collision_approval.py` (append)

- [ ] **Step 1: Write the failing tests for collision service**

Append to `tests/test_p11_collision_approval.py`:

```python
from projects.services.collision import compute_title_similarity, detect_collisions


class TestTitleSimilarity:
    def test_identical_titles(self):
        assert compute_title_similarity("품질기획팀장", "품질기획팀장") == 1.0

    def test_very_similar_titles(self):
        score = compute_title_similarity("품질기획팀장", "품질기획파트장")
        assert score >= 0.7  # high similarity

    def test_same_department_different_role(self):
        score = compute_title_similarity("경영기획팀장", "경영기획")
        assert score >= 0.5

    def test_completely_different(self):
        score = compute_title_similarity("품질기획팀장", "마케팅매니저")
        assert score < 0.5

    def test_empty_title(self):
        assert compute_title_similarity("", "품질기획팀장") == 0.0
        assert compute_title_similarity("품질기획팀장", "") == 0.0


class TestDetectCollisions:
    @pytest.mark.django_db
    def test_detects_similar_project(self, org, client_obj, existing_project):
        results = detect_collisions(client_obj.pk, "품질기획파트장", org)
        assert len(results) >= 1
        assert results[0]["project"].pk == existing_project.pk
        assert results[0]["score"] >= 0.7
        assert results[0]["conflict_type"] == "높은중복"

    @pytest.mark.django_db
    def test_no_collision_different_client(self, org, client_obj, existing_project):
        other_client = Client.objects.create(
            name="Other Corp", industry="Finance", organization=org
        )
        results = detect_collisions(other_client.pk, "품질기획팀장", org)
        assert len(results) == 0

    @pytest.mark.django_db
    def test_excludes_closed_projects(self, org, client_obj, user_consultant):
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="품질기획팀장",
            status="closed_success",
            created_by=user_consultant,
        )
        results = detect_collisions(client_obj.pk, "품질기획팀장", org)
        assert len(results) == 0

    @pytest.mark.django_db
    def test_medium_conflict_type(self, org, client_obj, existing_project):
        results = detect_collisions(client_obj.pk, "마케팅매니저", org)
        # Same client but low similarity -> medium or no result
        for r in results:
            if r["score"] < 0.7:
                assert r["conflict_type"] == "참고정보"

    @pytest.mark.django_db
    def test_max_five_results(self, org, client_obj, user_consultant):
        for i in range(8):
            Project.objects.create(
                client=client_obj,
                organization=org,
                title=f"품질기획팀장{i}",
                status="searching",
                created_by=user_consultant,
            )
        results = detect_collisions(client_obj.pk, "품질기획팀장", org)
        assert len(results) <= 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestTitleSimilarity tests/test_p11_collision_approval.py::TestDetectCollisions -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement collision service**

Create `projects/services/collision.py`:

```python
"""Collision detection for project registration."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from projects.models import Project, ProjectStatus


# Closed statuses — projects with these statuses are excluded from collision checks
CLOSED_STATUSES = {
    ProjectStatus.CLOSED_SUCCESS,
    ProjectStatus.CLOSED_FAIL,
    ProjectStatus.CLOSED_CANCEL,
}


def compute_title_similarity(title_a: str, title_b: str) -> float:
    """
    Compute similarity score between two project titles.

    Strategy:
    1. Extract keywords by splitting Korean compound words at common suffixes
    2. Use SequenceMatcher for overall similarity
    3. Boost score when core keywords match

    Returns float 0.0 ~ 1.0.
    """
    if not title_a or not title_b:
        return 0.0

    a_norm = _normalize(title_a)
    b_norm = _normalize(title_b)

    # Base similarity via SequenceMatcher
    base_score = SequenceMatcher(None, a_norm, b_norm).ratio()

    # Keyword extraction and matching for boost
    kw_a = _extract_keywords(a_norm)
    kw_b = _extract_keywords(b_norm)

    if kw_a and kw_b:
        common = kw_a & kw_b
        total = kw_a | kw_b
        keyword_score = len(common) / len(total) if total else 0.0
        # Weighted combination: 40% base, 60% keyword
        return min(1.0, 0.4 * base_score + 0.6 * keyword_score)

    return base_score


def _normalize(title: str) -> str:
    """Normalize title: lowercase, strip whitespace, remove common noise."""
    title = title.strip().lower()
    # Remove common parenthetical suffixes like (정규직), (계약직)
    title = re.sub(r"\s*\(.*?\)\s*", "", title)
    return title


# Common Korean role/position suffixes for splitting compound words
_ROLE_SUFFIXES = [
    "팀장", "파트장", "실장", "센터장", "본부장", "부장", "차장", "과장",
    "대리", "사원", "매니저", "리더", "담당", "책임", "수석", "선임",
    "이사", "상무", "전무", "부사장", "사장",
]

# Common department keywords
_DEPT_KEYWORDS = [
    "기획", "영업", "마케팅", "인사", "재무", "회계", "총무", "법무",
    "개발", "연구", "생산", "품질", "물류", "구매", "경영", "전략",
    "디자인", "IT", "보안", "감사",
]


def _extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a normalized title."""
    keywords = set()

    # Check for role suffixes
    for suffix in _ROLE_SUFFIXES:
        if suffix in title:
            keywords.add(suffix)
            # Also extract the prefix before the suffix as a keyword
            idx = title.find(suffix)
            prefix = title[:idx].strip()
            if prefix:
                keywords.add(prefix)

    # Check for department keywords
    for dept in _DEPT_KEYWORDS:
        if dept in title:
            keywords.add(dept)

    # If no keywords found, use the whole title as one keyword
    if not keywords:
        keywords.add(title)

    return keywords


def detect_collisions(
    client_id,
    title: str,
    org,
    exclude_project_id=None,
) -> list[dict]:
    """
    Detect similar projects for a given client and title.

    Returns list of dicts sorted by score descending, max 5 items:
    [
        {
            "project": Project,
            "score": float,
            "conflict_type": "높은중복" | "참고정보",
            "consultant_name": str,
            "status_display": str,
        },
        ...
    ]
    """
    # Fetch active projects for this client in the same org
    candidates = Project.objects.filter(
        client_id=client_id,
        organization=org,
    ).exclude(
        status__in=CLOSED_STATUSES,
    ).select_related("created_by")

    if exclude_project_id:
        candidates = candidates.exclude(pk=exclude_project_id)

    results = []
    for proj in candidates:
        score = compute_title_similarity(title, proj.title)
        if score > 0.0:
            conflict_type = "높은중복" if score >= 0.7 else "참고정보"
            consultant_name = ""
            if proj.created_by:
                consultant_name = (
                    proj.created_by.get_full_name() or proj.created_by.username
                )
            results.append({
                "project": proj,
                "score": round(score, 2),
                "conflict_type": conflict_type,
                "consultant_name": consultant_name,
                "status_display": proj.get_status_display(),
            })

    # Sort by score descending, take top 5
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:5]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestTitleSimilarity tests/test_p11_collision_approval.py::TestDetectCollisions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/collision.py tests/test_p11_collision_approval.py
git commit -m "feat(p11): add collision detection service with title similarity scoring"
```

---

### Task 3: Service — Approval state transitions

**Files:**
- Create: `projects/services/approval.py`
- Test: `tests/test_p11_collision_approval.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p11_collision_approval.py`:

```python
from projects.services.approval import (
    InvalidApprovalTransition,
    approve_project,
    cancel_approval,
    merge_project,
    reject_project,
    send_admin_message,
)


class TestApprovalService:
    @pytest.fixture
    def pending_project(self, org, client_obj, user_consultant):
        return Project.objects.create(
            client=client_obj,
            organization=org,
            title="품질기획파트장",
            status="pending_approval",
            created_by=user_consultant,
        )

    @pytest.fixture
    def approval(self, pending_project, user_consultant, existing_project):
        return ProjectApproval.objects.create(
            project=pending_project,
            requested_by=user_consultant,
            conflict_project=existing_project,
            conflict_score=0.85,
            conflict_type="높은중복",
        )

    @pytest.mark.django_db
    def test_approve_project(self, approval, user_owner, pending_project):
        approve_project(approval, user_owner)
        approval.refresh_from_db()
        pending_project.refresh_from_db()
        assert approval.status == "승인"
        assert pending_project.status == "new"
        assert approval.decided_by == user_owner
        assert approval.decided_at is not None

    @pytest.mark.django_db
    def test_reject_project(self, approval, user_owner, pending_project):
        reject_project(approval, user_owner, response_text="중복 프로젝트입니다.")
        approval.refresh_from_db()
        assert approval.status == "반려"
        assert approval.admin_response == "중복 프로젝트입니다."
        # Project should be deleted
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_merge_project(self, approval, user_owner, pending_project, existing_project, user_consultant):
        merge_project(approval, user_owner, merge_target=existing_project)
        approval.refresh_from_db()
        assert approval.status == "합류"
        # Requester should be added to target project
        assert existing_project.assigned_consultants.filter(pk=user_consultant.pk).exists()
        # Pending project should be deleted
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_merge_defaults_to_conflict_project(self, approval, user_owner, pending_project, existing_project, user_consultant):
        merge_project(approval, user_owner)  # No merge_target
        existing_project.refresh_from_db()
        assert existing_project.assigned_consultants.filter(pk=user_consultant.pk).exists()

    @pytest.mark.django_db
    def test_send_admin_message(self, approval, user_owner):
        send_admin_message(approval, user_owner, "추가 정보를 제공해주세요.")
        approval.refresh_from_db()
        assert approval.admin_response == "추가 정보를 제공해주세요."
        assert approval.status == "대기"  # Status unchanged

    @pytest.mark.django_db
    def test_cancel_approval(self, approval, pending_project):
        cancel_approval(approval)
        assert not ProjectApproval.objects.filter(pk=approval.pk).exists()
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_double_approve_raises(self, approval, user_owner):
        approve_project(approval, user_owner)
        with pytest.raises(InvalidApprovalTransition):
            approve_project(approval, user_owner)

    @pytest.mark.django_db
    def test_reject_after_approve_raises(self, approval, user_owner):
        approve_project(approval, user_owner)
        with pytest.raises(InvalidApprovalTransition):
            reject_project(approval, user_owner)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestApprovalService -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement approval service**

Create `projects/services/approval.py`:

```python
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
    # Terminal states — no further transitions allowed
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
    project.status = ProjectStatus.NEW
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
    approval.save(update_fields=["status", "decided_by", "decided_at", "admin_response"])

    # Delete the pending project (safe — pending_approval blocks downstream data)
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
        raise InvalidApprovalTransition(
            "대기 상태에서만 메시지를 보낼 수 있습니다."
        )
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
    _safe_delete_pending_project(project)


def _safe_delete_pending_project(project: Project) -> None:
    """Delete a pending_approval project. Raises if downstream data exists."""
    if project.contacts.exists() or project.submissions.exists():
        raise InvalidApprovalTransition(
            "하위 데이터(컨택/제출)가 존재하여 삭제할 수 없습니다."
        )
    project.delete()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestApprovalService -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/approval.py tests/test_p11_collision_approval.py
git commit -m "feat(p11): add approval state transition service"
```

---

### Task 4: Form changes — Remove status from ProjectForm, add ApprovalDecisionForm

**Files:**
- Modify: `projects/forms.py:15-75`
- Test: `tests/test_p11_collision_approval.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p11_collision_approval.py`:

```python
from projects.forms import ApprovalDecisionForm, ProjectForm


class TestProjectFormNoStatus:
    @pytest.mark.django_db
    def test_status_not_in_form_fields(self, org):
        form = ProjectForm(organization=org)
        assert "status" not in form.fields


class TestApprovalDecisionForm:
    def test_valid_approve(self):
        form = ApprovalDecisionForm(data={"decision": "승인"})
        assert form.is_valid()

    def test_valid_reject_with_response(self):
        form = ApprovalDecisionForm(data={"decision": "반려", "response_text": "중복입니다."})
        assert form.is_valid()

    def test_valid_message(self):
        form = ApprovalDecisionForm(data={"decision": "메시지", "response_text": "추가 정보 필요"})
        assert form.is_valid()

    def test_invalid_decision(self):
        form = ApprovalDecisionForm(data={"decision": "invalid"})
        assert not form.is_valid()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestProjectFormNoStatus tests/test_p11_collision_approval.py::TestApprovalDecisionForm -v`
Expected: FAIL

- [ ] **Step 3: Modify ProjectForm and add ApprovalDecisionForm**

In `projects/forms.py`, modify `ProjectForm.Meta.fields`:

```python
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["client", "title", "jd_source", "jd_text", "jd_file"]
        # ...existing widgets and labels, but remove "status" entries...
```

Remove `"status"` from `fields`, `widgets`, and `labels`.

Add at the end of `projects/forms.py`:

```python
# ---------------------------------------------------------------------------
# P11: Approval forms
# ---------------------------------------------------------------------------

DECISION_CHOICES = [
    ("승인", "승인"),
    ("합류", "합류"),
    ("메시지", "메시지"),
    ("반려", "반려"),
]


class ApprovalDecisionForm(forms.Form):
    """관리자 승인 판단 폼."""

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CSS}),
        label="판단",
    )
    response_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "placeholder": "메시지 또는 반려 사유",
            }
        ),
        label="메시지",
        required=False,
    )
    merge_target = forms.UUIDField(required=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestProjectFormNoStatus tests/test_p11_collision_approval.py::TestApprovalDecisionForm -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/forms.py tests/test_p11_collision_approval.py
git commit -m "feat(p11): remove status from ProjectForm, add ApprovalDecisionForm"
```

---

### Task 5: Views — Collision check endpoint + project_create modification

**Files:**
- Modify: `projects/views.py:0-196`
- Modify: `projects/urls.py`
- Create: `projects/templates/projects/partials/collision_warning.html`
- Modify: `projects/templates/projects/project_form.html`
- Test: `tests/test_p11_collision_approval.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p11_collision_approval.py`:

```python
class TestCollisionCheckView:
    @pytest.mark.django_db
    def test_collision_detected(self, auth_consultant, client_obj, existing_project):
        resp = auth_consultant.post(
            "/projects/new/check-collision/",
            {"client_id": str(client_obj.pk), "title": "품질기획파트장"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert "높은 중복" in resp.content.decode() or "충돌" in resp.content.decode()

    @pytest.mark.django_db
    def test_no_collision(self, auth_consultant, client_obj):
        resp = auth_consultant.post(
            "/projects/new/check-collision/",
            {"client_id": str(client_obj.pk), "title": "완전다른포지션"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200


class TestProjectCreateWithCollision:
    @pytest.mark.django_db
    def test_create_without_collision_normal(self, auth_consultant, client_obj):
        """No collision -> status=new, direct redirect."""
        resp = auth_consultant.post("/projects/new/", {
            "client": str(client_obj.pk),
            "title": "완전새로운포지션",
            "jd_source": "",
        })
        assert resp.status_code == 302
        project = Project.objects.get(title="완전새로운포지션")
        assert project.status == "new"
        assert not ProjectApproval.objects.filter(project=project).exists()

    @pytest.mark.django_db
    def test_create_with_high_collision(self, auth_consultant, client_obj, existing_project, user_consultant):
        """High collision -> pending_approval + ProjectApproval created."""
        resp = auth_consultant.post("/projects/new/", {
            "client": str(client_obj.pk),
            "title": "품질기획파트장",
            "jd_source": "",
        })
        project = Project.objects.get(title="품질기획파트장")
        assert project.status == "pending_approval"
        approval = ProjectApproval.objects.get(project=project)
        assert approval.conflict_project == existing_project
        assert approval.conflict_score >= 0.7
        assert approval.requested_by == user_consultant
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestCollisionCheckView tests/test_p11_collision_approval.py::TestProjectCreateWithCollision -v`
Expected: FAIL

- [ ] **Step 3: Add collision check view**

In `projects/views.py`, add import at top:

```python
from .models import (
    # ...existing imports...
    ProjectApproval,
)
```

Add the collision check view:

```python
@login_required
@require_http_methods(["POST"])
def project_check_collision(request):
    """HTMX endpoint: check for collision when client + title are provided."""
    org = _get_org(request)
    client_id = request.POST.get("client_id")
    title = request.POST.get("title", "").strip()

    if not client_id or not title:
        return HttpResponse("")

    from projects.services.collision import detect_collisions

    collisions = detect_collisions(client_id, title, org)

    high_collisions = [c for c in collisions if c["conflict_type"] == "높은중복"]
    medium_collisions = [c for c in collisions if c["conflict_type"] == "참고정보"]

    return render(
        request,
        "projects/partials/collision_warning.html",
        {
            "high_collisions": high_collisions,
            "medium_collisions": medium_collisions,
            "has_blocking_collision": len(high_collisions) > 0,
        },
    )
```

- [ ] **Step 4: Modify project_create view**

Replace the `project_create` view:

```python
@login_required
def project_create(request):
    """Create a new project. GET=form, POST=save with collision detection."""
    org = _get_org(request)

    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, organization=org)
        if form.is_valid():
            from django.db import transaction
            from projects.services.collision import detect_collisions

            client_id = form.cleaned_data["client"].pk
            title = form.cleaned_data["title"]
            collisions = detect_collisions(client_id, title, org)

            high_collisions = [c for c in collisions if c["conflict_type"] == "높은중복"]

            with transaction.atomic():
                project = form.save(commit=False)
                project.organization = org
                project.created_by = request.user

                if high_collisions:
                    # Collision detected -> pending_approval
                    project.status = ProjectStatus.PENDING_APPROVAL
                    project.save()
                    project.assigned_consultants.add(request.user)

                    top_collision = high_collisions[0]
                    ProjectApproval.objects.create(
                        project=project,
                        requested_by=request.user,
                        conflict_project=top_collision["project"],
                        conflict_score=top_collision["score"],
                        conflict_type=top_collision["conflict_type"],
                        message=request.POST.get("approval_message", ""),
                    )
                    return render(
                        request,
                        "projects/project_form.html",
                        {
                            "form": form,
                            "is_edit": False,
                            "approval_submitted": True,
                            "project": project,
                        },
                    )
                else:
                    # No blocking collision -> normal create
                    project.save()
                    project.assigned_consultants.add(request.user)
                    return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm(organization=org)

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "is_edit": False},
    )
```

- [ ] **Step 5: Add URL patterns**

In `projects/urls.py`, add at the beginning of `urlpatterns`:

```python
    # P11: Collision check
    path(
        "new/check-collision/",
        views.project_check_collision,
        name="project_check_collision",
    ),
```

**Important:** This must be placed before `path("new/", ...)` to avoid URL conflicts.

- [ ] **Step 6: Create collision warning template**

Create `projects/templates/projects/partials/collision_warning.html`:

```html
{% if high_collisions %}
<div class="bg-red-50 border border-red-200 rounded-lg p-4 space-y-3">
  <div class="flex items-center gap-2 text-red-700 font-semibold text-[15px]">
    <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
    유사 프로젝트가 감지되었습니다
  </div>
  {% for c in high_collisions %}
  <div class="bg-white rounded border border-red-100 p-3 text-[14px] space-y-1">
    <div class="font-medium text-gray-900">{{ c.project.client.name }} · {{ c.project.title }}</div>
    <div class="text-gray-500">담당: {{ c.consultant_name }} ({{ c.status_display }})</div>
    <div class="text-red-600 font-medium">유사도: {{ c.score }}</div>
  </div>
  {% endfor %}
  <p class="text-[13px] text-red-600">
    등록 시 관리자 승인이 필요합니다. 아래에 요청 사유를 입력해 주세요.
  </p>
  <div>
    <label for="approval_message" class="block text-[13px] text-gray-700 font-medium mb-1">요청 메시지 (선택)</label>
    <textarea name="approval_message" id="approval_message" rows="2"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 text-[14px] focus:ring-2 focus:ring-primary focus:border-primary"
              placeholder="승인 요청 사유를 입력하세요..."></textarea>
  </div>
</div>
{% endif %}

{% if medium_collisions %}
<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 space-y-2">
  <div class="flex items-center gap-2 text-yellow-700 font-medium text-[14px]">
    <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
    참고: 같은 고객사의 진행 중 프로젝트
  </div>
  {% for c in medium_collisions %}
  <div class="text-[13px] text-gray-600">
    {{ c.project.title }} — {{ c.consultant_name }} ({{ c.status_display }})
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 7: Update project_form.html for HTMX collision check**

Replace `projects/templates/projects/project_form.html`:

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}{% if is_edit %}프로젝트 수정{% else %}프로젝트 등록{% endif %} — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">

  <!-- Back -->
  <div>
    {% if is_edit %}
    <a href="{% url 'projects:project_detail' project.pk %}"
       hx-get="{% url 'projects:project_detail' project.pk %}" hx-target="#main-content" hx-push-url="true"
       class="flex items-center gap-1 text-[15px] text-gray-500 hover:text-gray-700 transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      상세로 돌아가기
    </a>
    {% elif approval_submitted %}
    <a href="{% url 'projects:project_list' %}"
       hx-get="{% url 'projects:project_list' %}" hx-target="#main-content" hx-push-url="true"
       class="flex items-center gap-1 text-[15px] text-gray-500 hover:text-gray-700 transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      목록으로 돌아가기
    </a>
    {% else %}
    <a href="{% url 'projects:project_list' %}"
       hx-get="{% url 'projects:project_list' %}" hx-target="#main-content" hx-push-url="true"
       class="flex items-center gap-1 text-[15px] text-gray-500 hover:text-gray-700 transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      목록으로 돌아가기
    </a>
    {% endif %}
  </div>

  {% if approval_submitted %}
  <!-- Approval submitted confirmation -->
  <div class="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center space-y-3">
    <div class="text-blue-700 font-semibold text-[17px]">승인 요청이 제출되었습니다</div>
    <p class="text-[15px] text-gray-600">
      유사 프로젝트가 감지되어 관리자 승인이 필요합니다.<br>
      승인 후 프로젝트가 활성화됩니다.
    </p>
    <a href="{% url 'projects:project_list' %}"
       hx-get="{% url 'projects:project_list' %}" hx-target="#main-content" hx-push-url="true"
       class="inline-block bg-primary text-white font-semibold py-2.5 px-6 rounded-lg text-[15px] hover:bg-primary-dark transition">
      목록으로 돌아가기
    </a>
  </div>
  {% else %}

  <!-- Title -->
  <h1 class="text-heading font-bold">{% if is_edit %}프로젝트 수정{% else %}프로젝트 등록{% endif %}</h1>

  <!-- Form -->
  <form method="post" enctype="multipart/form-data" class="space-y-6">
    {% csrf_token %}

    <!-- Fields -->
    <section class="bg-white rounded-lg border border-gray-100 p-5 space-y-4">
      <h2 class="text-[15px] font-semibold text-gray-500">프로젝트 정보</h2>

      {% for field in form %}
      <div>
        <label for="{{ field.id_for_label }}" class="block text-[15px] text-gray-700 font-medium mb-1">
          {{ field.label }}{% if field.field.required %} <span class="text-red-500">*</span>{% endif %}
        </label>
        {{ field }}
        {% if field.errors %}
        <p class="text-[13px] text-red-500 mt-1">{{ field.errors.0 }}</p>
        {% endif %}
      </div>
      {% endfor %}
    </section>

    <!-- Collision Warning Area -->
    <div id="collision-warning"></div>

    <!-- Submit -->
    <div class="flex gap-3">
      <button type="submit"
              class="flex-1 bg-primary text-white font-semibold py-3 rounded-lg text-[15px] hover:bg-primary-dark transition">
        {% if is_edit %}저장{% else %}등록{% endif %}
      </button>
    </div>
  </form>

  {% if not is_edit %}
  <script>
  (function() {
    const clientField = document.getElementById('id_client');
    const titleField = document.getElementById('id_title');
    const warningArea = document.getElementById('collision-warning');

    function checkCollision() {
      const clientId = clientField ? clientField.value : '';
      const title = titleField ? titleField.value.trim() : '';
      if (!clientId || !title) {
        warningArea.innerHTML = '';
        return;
      }
      htmx.ajax('POST', '{% url "projects:project_check_collision" %}', {
        target: '#collision-warning',
        swap: 'innerHTML',
        values: {
          client_id: clientId,
          title: title,
          csrfmiddlewaretoken: document.querySelector('[name=csrfmiddlewaretoken]').value,
        },
      });
    }

    if (clientField) clientField.addEventListener('change', checkCollision);
    if (titleField) titleField.addEventListener('blur', checkCollision);
  })();
  </script>
  {% endif %}

  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestCollisionCheckView tests/test_p11_collision_approval.py::TestProjectCreateWithCollision -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add projects/views.py projects/urls.py projects/templates/projects/partials/collision_warning.html projects/templates/projects/project_form.html tests/test_p11_collision_approval.py
git commit -m "feat(p11): add collision detection to project creation flow"
```

---

### Task 6: Views — Approval queue + decide + cancel + pending_approval guards

**Files:**
- Modify: `projects/views.py`
- Modify: `projects/urls.py`
- Create: `projects/templates/projects/approval_queue.html`
- Create: `projects/templates/projects/partials/approval_card.html`
- Test: `tests/test_p11_collision_approval.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p11_collision_approval.py`:

```python
class TestApprovalQueueView:
    @pytest.fixture
    def pending_project(self, org, client_obj, user_consultant):
        return Project.objects.create(
            client=client_obj,
            organization=org,
            title="품질기획파트장",
            status="pending_approval",
            created_by=user_consultant,
        )

    @pytest.fixture
    def approval(self, pending_project, user_consultant, existing_project):
        return ProjectApproval.objects.create(
            project=pending_project,
            requested_by=user_consultant,
            conflict_project=existing_project,
            conflict_score=0.85,
            conflict_type="높은중복",
            message="인사팀으로부터 직접 의뢰",
        )

    @pytest.mark.django_db
    def test_owner_can_access_queue(self, auth_owner, approval):
        resp = auth_owner.get("/projects/approvals/")
        assert resp.status_code == 200
        assert "품질기획파트장" in resp.content.decode()

    @pytest.mark.django_db
    def test_consultant_cannot_access_queue(self, auth_consultant, approval):
        resp = auth_consultant.get("/projects/approvals/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_approve_decision(self, auth_owner, approval, pending_project):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "승인"},
        )
        assert resp.status_code == 302
        pending_project.refresh_from_db()
        assert pending_project.status == "new"

    @pytest.mark.django_db
    def test_reject_decision(self, auth_owner, approval, pending_project):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "반려", "response_text": "중복입니다."},
        )
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_merge_decision(self, auth_owner, approval, pending_project, existing_project, user_consultant):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "합류"},
        )
        assert resp.status_code == 302
        assert existing_project.assigned_consultants.filter(pk=user_consultant.pk).exists()
        assert not Project.objects.filter(pk=pending_project.pk).exists()


class TestApprovalCancelView:
    @pytest.fixture
    def pending_project(self, org, client_obj, user_consultant):
        return Project.objects.create(
            client=client_obj,
            organization=org,
            title="품질기획파트장",
            status="pending_approval",
            created_by=user_consultant,
        )

    @pytest.fixture
    def approval(self, pending_project, user_consultant):
        return ProjectApproval.objects.create(
            project=pending_project,
            requested_by=user_consultant,
        )

    @pytest.mark.django_db
    def test_requester_can_cancel(self, auth_consultant, approval, pending_project):
        resp = auth_consultant.post(f"/projects/{pending_project.pk}/approval/cancel/")
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=pending_project.pk).exists()
        assert not ProjectApproval.objects.filter(pk=approval.pk).exists()


class TestPendingApprovalGuards:
    @pytest.fixture
    def pending_project(self, org, client_obj, user_consultant):
        p = Project.objects.create(
            client=client_obj,
            organization=org,
            title="승인대기프로젝트",
            status="pending_approval",
            created_by=user_consultant,
        )
        p.assigned_consultants.add(user_consultant)
        return p

    @pytest.mark.django_db
    def test_contact_create_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.get(f"/projects/{pending_project.pk}/contacts/new/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_submission_create_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.get(f"/projects/{pending_project.pk}/submissions/new/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_status_update_blocked(self, auth_consultant, pending_project):
        import json
        resp = auth_consultant.patch(
            f"/projects/{pending_project.pk}/status/",
            json.dumps({"status": "new"}),
            content_type="application/json",
        )
        assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestApprovalQueueView tests/test_p11_collision_approval.py::TestApprovalCancelView tests/test_p11_collision_approval.py::TestPendingApprovalGuards -v`
Expected: FAIL

- [ ] **Step 3: Add helper to check OWNER role**

In `projects/views.py`, add helper function:

```python
def _is_owner(request):
    """Check if the current user has OWNER role in their organization."""
    from accounts.models import Membership
    try:
        return request.user.membership.role == Membership.Role.OWNER
    except Membership.DoesNotExist:
        return False
```

- [ ] **Step 4: Add approval queue view**

In `projects/views.py`:

```python
@login_required
def approval_queue(request):
    """OWNER-only: list pending approval requests."""
    org = _get_org(request)

    if not _is_owner(request):
        return HttpResponse(status=403)

    approvals = ProjectApproval.objects.filter(
        project__organization=org,
        status=ProjectApproval.Status.PENDING,
    ).select_related(
        "project", "project__client", "requested_by",
        "conflict_project", "conflict_project__client",
    ).order_by("-created_at")

    return render(
        request,
        "projects/approval_queue.html",
        {"approvals": approvals, "approval_count": approvals.count()},
    )
```

- [ ] **Step 5: Add approval decide view**

In `projects/views.py`:

```python
@login_required
@require_http_methods(["POST"])
def approval_decide(request, appr_pk):
    """OWNER-only: decide on an approval request."""
    org = _get_org(request)

    if not _is_owner(request):
        return HttpResponse(status=403)

    from .forms import ApprovalDecisionForm
    from .services.approval import (
        InvalidApprovalTransition,
        approve_project,
        merge_project,
        reject_project,
        send_admin_message,
    )

    approval = get_object_or_404(
        ProjectApproval,
        pk=appr_pk,
        project__organization=org,
    )

    form = ApprovalDecisionForm(request.POST)
    if not form.is_valid():
        return redirect("projects:approval_queue")

    decision = form.cleaned_data["decision"]
    response_text = form.cleaned_data.get("response_text", "")
    merge_target_id = form.cleaned_data.get("merge_target")

    try:
        if decision == "승인":
            approve_project(approval, request.user)
        elif decision == "합류":
            merge_target = None
            if merge_target_id:
                merge_target = get_object_or_404(
                    Project, pk=merge_target_id, organization=org
                )
            merge_project(approval, request.user, merge_target=merge_target)
        elif decision == "메시지":
            send_admin_message(approval, request.user, response_text)
        elif decision == "반려":
            reject_project(approval, request.user, response_text=response_text)
    except InvalidApprovalTransition:
        pass  # Already handled — redirect back to queue

    return redirect("projects:approval_queue")
```

- [ ] **Step 6: Add approval cancel view**

In `projects/views.py`:

```python
@login_required
@require_http_methods(["POST"])
def approval_cancel(request, pk):
    """Requester cancels their approval request."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    approval = get_object_or_404(
        ProjectApproval,
        project=project,
        requested_by=request.user,
        status=ProjectApproval.Status.PENDING,
    )

    from .services.approval import cancel_approval
    cancel_approval(approval)

    return redirect("projects:project_list")
```

- [ ] **Step 7: Add pending_approval guards to existing views**

Add this guard to `status_update`, `contact_create`, `submission_create`, `interview_create`, `offer_create` views. After `project = get_object_or_404(...)`:

```python
    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)
```

For `status_update`, also add a check to prevent transitioning TO or FROM `pending_approval`:

```python
    # Block any status change for pending_approval projects
    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)
    if new_status == ProjectStatus.PENDING_APPROVAL:
        return JsonResponse({"error": "invalid status"}, status=400)
```

- [ ] **Step 8: Add URL patterns**

In `projects/urls.py`, add:

```python
    # P11: Approval workflow
    path(
        "<uuid:pk>/approval/cancel/",
        views.approval_cancel,
        name="approval_cancel",
    ),
    path(
        "approvals/",
        views.approval_queue,
        name="approval_queue",
    ),
    path(
        "approvals/<uuid:appr_pk>/decide/",
        views.approval_decide,
        name="approval_decide",
    ),
```

- [ ] **Step 9: Create approval_queue.html template**

Create `projects/templates/projects/approval_queue.html`:

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}승인 요청 — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">

  <div class="flex items-center justify-between">
    <h1 class="text-heading font-bold">승인 요청 ({{ approval_count }}건)</h1>
    <a href="{% url 'projects:project_list' %}"
       hx-get="{% url 'projects:project_list' %}" hx-target="#main-content" hx-push-url="true"
       class="text-[15px] text-gray-500 hover:text-gray-700 transition">
      프로젝트 목록
    </a>
  </div>

  {% if approvals %}
  <div class="space-y-4">
    {% for approval in approvals %}
    {% include "projects/partials/approval_card.html" with approval=approval %}
    {% endfor %}
  </div>
  {% else %}
  <div class="bg-gray-50 rounded-lg p-8 text-center text-gray-500 text-[15px]">
    대기 중인 승인 요청이 없습니다.
  </div>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 10: Create approval_card.html partial**

Create `projects/templates/projects/partials/approval_card.html`:

```html
<div class="bg-white rounded-lg border border-gray-200 p-5 space-y-3">
  <div class="flex items-start justify-between">
    <div>
      <div class="text-[16px] font-semibold text-gray-900">
        {{ approval.requested_by.get_full_name|default:approval.requested_by.username }}
        &rarr; {{ approval.project.client.name }} &middot; {{ approval.project.title }}
      </div>
      {% if approval.conflict_project %}
      <div class="text-[14px] text-gray-500 mt-1">
        충돌: {{ approval.conflict_project.created_by.get_full_name|default:approval.conflict_project.created_by.username }}의
        "{{ approval.conflict_project.client.name }} &middot; {{ approval.conflict_project.title }}"
        ({{ approval.conflict_project.get_status_display }})
      </div>
      <div class="text-[14px] mt-1 {% if approval.conflict_score >= 0.7 %}text-red-600 font-medium{% else %}text-yellow-600{% endif %}">
        유사도: {% if approval.conflict_score >= 0.7 %}높음{% else %}중간{% endif %}
        ({{ approval.conflict_score }})
      </div>
      {% endif %}
    </div>
    <div class="text-[13px] text-gray-400">{{ approval.created_at|date:"m/d" }}</div>
  </div>

  {% if approval.message %}
  <div class="bg-gray-50 rounded p-3 text-[14px] text-gray-700">
    "{{ approval.message }}"
  </div>
  {% endif %}

  {% if approval.admin_response %}
  <div class="bg-blue-50 rounded p-3 text-[14px] text-blue-700">
    관리자: "{{ approval.admin_response }}"
  </div>
  {% endif %}

  <form method="post" action="{% url 'projects:approval_decide' appr_pk=approval.pk %}" class="flex flex-wrap gap-2">
    {% csrf_token %}
    <button type="submit" name="decision" value="승인"
            class="px-4 py-2 bg-green-600 text-white rounded-lg text-[14px] font-medium hover:bg-green-700 transition">
      승인
    </button>
    <button type="submit" name="decision" value="합류"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg text-[14px] font-medium hover:bg-blue-700 transition">
      합류
    </button>
    <button type="submit" name="decision" value="반려"
            class="px-4 py-2 bg-red-600 text-white rounded-lg text-[14px] font-medium hover:bg-red-700 transition"
            onclick="var reason = prompt('반려 사유를 입력해 주세요.'); if(reason === null) return false; this.form.querySelector('[name=response_text]').value = reason;">
      반려
    </button>
    <input type="hidden" name="response_text" value="">
  </form>
</div>
```

- [ ] **Step 11: Run tests to verify they pass**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestApprovalQueueView tests/test_p11_collision_approval.py::TestApprovalCancelView tests/test_p11_collision_approval.py::TestPendingApprovalGuards -v`
Expected: PASS

- [ ] **Step 12: Run full test suite**

Run: `uv run pytest tests/test_p11_collision_approval.py -v`
Expected: All tests PASS

- [ ] **Step 13: Run existing tests to check for regressions**

Run: `uv run pytest tests/test_projects_views.py -v`
Expected: PASS (may need to fix tests that depended on `status` being in ProjectForm)

- [ ] **Step 14: Commit**

```bash
git add projects/views.py projects/urls.py projects/templates/projects/approval_queue.html projects/templates/projects/partials/approval_card.html tests/test_p11_collision_approval.py
git commit -m "feat(p11): add approval queue, decide, cancel views with pending_approval guards"
```

---

### Task 7: Full integration test + regression fix

**Files:**
- Test: `tests/test_p11_collision_approval.py` (final verification)
- Modify: `tests/test_projects_views.py` (fix any regressions from `status` removal)

- [ ] **Step 1: Run the full project test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: Identify any failures from removing `status` from `ProjectForm`

- [ ] **Step 2: Fix any regressions**

If `tests/test_projects_views.py` has tests that set `status` via `ProjectForm`, remove those `status` values from the POST data. Projects now always start as `status="new"` unless collision is detected.

For any test that uses `auth_client.post("/projects/new/", {..., "status": "new"})`, remove the `"status": "new"` from the data dict.

- [ ] **Step 3: Run full suite again**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit regression fixes if any**

```bash
git add tests/
git commit -m "fix(p11): fix test regressions from ProjectForm status removal"
```

---

### Task 8: Lint and format

- [ ] **Step 1: Run ruff**

```bash
uv run ruff check projects/services/collision.py projects/services/approval.py projects/views.py projects/forms.py projects/models.py projects/admin.py tests/test_p11_collision_approval.py --fix
uv run ruff format projects/services/collision.py projects/services/approval.py projects/views.py projects/forms.py projects/models.py projects/admin.py tests/test_p11_collision_approval.py
```

- [ ] **Step 2: Run migration check**

```bash
uv run python manage.py makemigrations --check --dry-run
```
Expected: "No changes detected"

- [ ] **Step 3: Final commit if formatting changes**

```bash
git add -u
git commit -m "style(p11): apply ruff formatting"
```
