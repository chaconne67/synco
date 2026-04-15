# P11: Project Collision & Approval Implementation Plan (확정)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement collision detection on project creation and admin approval workflow so duplicate projects within the same client are reviewed before activation.

**Architecture:** Extend the existing `ProjectApproval` skeleton model with `conflict_score`, `conflict_type` fields and change `project` FK to `SET_NULL`. Add `collision.py` for title similarity matching and `approval.py` for state-transition logic. Modify `project_create` to detect collisions and route to approval flow. Add OWNER-only approval queue views under `/projects/approvals/`. Guard all project mutation views against `pending_approval` state.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Tailwind CSS

**Source documents:**
- 확정 설계서: `docs/forge/headhunting-workflow/p11/design-spec-agreed.md`
- 구현계획서 초안: `docs/forge/headhunting-workflow/p11/debate/impl-plan.md`
- 구현 쟁점 판정: `docs/forge/headhunting-workflow/p11/debate/impl-rulings.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `projects/models.py` | Modify | Add `ConflictType`, `conflict_score`/`conflict_type` to `ProjectApproval`, change project FK to SET_NULL |
| `projects/migrations/0007_p11_approval_collision_fields.py` | Create | Migration for new fields + FK alteration |
| `projects/services/collision.py` | Create | Title similarity scoring, collision detection |
| `projects/services/approval.py` | Create | Approval state transitions (approve/reject/merge/message/cancel) |
| `projects/forms.py` | Modify | Remove `status` from `ProjectForm`, add `ApprovalDecisionForm` |
| `projects/views.py` | Modify | Collision check, approval queue/decide/cancel, pending_approval guards on ALL mutation views |
| `projects/urls.py` | Modify | Add collision/approval URLs |
| `projects/admin.py` | Modify | Update `ProjectApprovalAdmin` with new fields |
| `projects/context_processors.py` | Create | Pending approval count for OWNER sidebar badge |
| `projects/templates/projects/partials/collision_warning.html` | Create | HTMX partial for collision detection results |
| `projects/templates/projects/project_form.html` | Modify | Add collision check HTMX + JS triggers + approval confirmation |
| `projects/templates/projects/approval_queue.html` | Create | Admin approval queue page |
| `projects/templates/projects/partials/approval_card.html` | Create | Approval card with message input + merge target dropdown |
| `projects/templates/projects/partials/view_board_card.html` | Modify | Add pending badge + cancel button |
| `projects/templates/projects/partials/view_list.html` | Modify | Add pending badge + cancel button |
| `projects/templates/projects/partials/view_table.html` | Modify | Add pending badge + cancel button |
| `templates/common/nav_sidebar.html` | Modify | Add OWNER approval badge |
| `main/settings.py` | Modify | Add context processor |
| `tests/test_p11_collision_approval.py` | Create | Full test suite |
| `tests/test_projects_views.py` | Modify | Fix regressions from status field removal |

---

## Critical Fixes from Implementation Tempering

The following fixes are incorporated from the `impl-rulings.md` and MUST be applied:

### Fix 1: ProjectApproval.project FK → SET_NULL (I-R1-01)
**Why:** Current `on_delete=CASCADE` means deleting a project cascades-deletes the approval record. Reject/merge need to delete the project while preserving the approval record for history.
**Change:** In Task 1, also alter the FK constraint: `on_delete=models.SET_NULL, null=True`.

### Fix 2: Guard project_delete for pending_approval (I-R1-02)
**Why:** Any org member can currently delete a pending_approval project via the normal delete endpoint, bypassing the approval flow.
**Change:** In Task 6, add `pending_approval` guard to `project_delete` view.

### Fix 3: Guard project_update for pending_approval (I-R1-03)
**Why:** Pending projects should be read-only per design spec.
**Change:** In Task 6, add `pending_approval` guard to `project_update` view.

### Fix 4: Message action in UI (I-R1-05)
**Why:** Approval card template originally only had approve/merge/reject buttons.
**Change:** In Task 6, add message textarea + send button to approval card.

### Fix 5: merge_target dropdown in UI (I-R1-06)
**Why:** Admin needs to select which project to merge into.
**Change:** In Task 6, add dropdown of same-client active projects to approval card. Pass candidates from approval_queue view.

### Fix 6: PRG pattern for high collision (I-R1-08)
**Why:** POST-then-render causes form resubmission risk.
**Change:** In Task 5, redirect to project_list after approval submission instead of rendering inline.

### Fix 7: Pending approval UI in project list (I-R1-09)
**Why:** Users need to see pending status and cancel button in project list.
**Change:** Add new Task (Task 7) for list template modifications.

### Fix 8: Sidebar badge for OWNER (I-R1-12)
**Why:** Design spec requires "승인 요청 (N건)" badge.
**Change:** Add new Task (Task 8) for context processor + sidebar modification.

---

### Task 1: Model — Add collision fields + fix FK

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

    @pytest.mark.django_db
    def test_project_fk_set_null_on_delete(self, org, client_obj, user_consultant, existing_project):
        """Verify that deleting the project sets FK to NULL instead of cascading."""
        approval = ProjectApproval.objects.create(
            project=existing_project,
            requested_by=user_consultant,
        )
        existing_project.delete()
        approval.refresh_from_db()
        assert approval.project is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p11_collision_approval.py::TestProjectApprovalModel -v`
Expected: FAIL

- [ ] **Step 3: Add ConflictType choices, fields, and change FK to SET_NULL**

In `projects/models.py`, add `ConflictType` above `ProjectApproval` class:

```python
class ConflictType(models.TextChoices):
    HIGH = "높은중복", "높은 중복 가능성"
    MEDIUM = "참고정보", "참고 정보"
```

Modify `ProjectApproval` class:
1. Change `project` FK from `on_delete=models.CASCADE` to `on_delete=models.SET_NULL, null=True, blank=True`
2. Add `conflict_score = models.FloatField(default=0.0)` after `conflict_project`
3. Add `conflict_type = models.CharField(max_length=20, choices=ConflictType.choices, blank=True, default="")` after `conflict_score`

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
git commit -m "feat(p11): add collision fields to ProjectApproval, change project FK to SET_NULL"
```

---

### Task 2: Service — Collision detection

Follow the original plan (debate/impl-plan.md Task 2) exactly. No changes needed.

**Files:**
- Create: `projects/services/collision.py`
- Test: `tests/test_p11_collision_approval.py` (append collision tests)

Code is provided in `debate/impl-plan.md` Task 2 Steps 1-5.

---

### Task 3: Service — Approval state transitions

Follow the original plan (debate/impl-plan.md Task 3) with these modifications:

**Files:**
- Create: `projects/services/approval.py`
- Test: `tests/test_p11_collision_approval.py` (append approval tests)

**Modification from original plan:**
- In `reject_project()` and `merge_project()`: The project deletion now sets `approval.project = NULL` via SET_NULL FK, so tests CAN call `approval.refresh_from_db()` after deletion.
- In `_safe_delete_pending_project()`: No change needed — it checks for downstream data before deletion.
- Test `test_reject_project`: After calling `reject_project()`, verify `approval.project is None` after refresh.
- Test `test_merge_project`: After calling `merge_project()`, verify `approval.project is None` after refresh.

---

### Task 4: Form changes

Follow the original plan (debate/impl-plan.md Task 4) exactly. No changes needed.

**Files:**
- Modify: `projects/forms.py`
- Test: `tests/test_p11_collision_approval.py` (append form tests)

---

### Task 5: Views — Collision check + project_create modification

Follow the original plan (debate/impl-plan.md Task 5) with these modifications:

**Files:**
- Modify: `projects/views.py`
- Modify: `projects/urls.py`
- Create: `projects/templates/projects/partials/collision_warning.html`
- Modify: `projects/templates/projects/project_form.html`
- Test: `tests/test_p11_collision_approval.py` (append view tests)

**Modification — PRG pattern (Fix 6):**

In the `project_create` view, when high collision is detected, instead of rendering inline, redirect:

```python
                    # After creating project + approval atomically:
                    from django.contrib import messages
                    messages.success(
                        request,
                        f"'{project.title}' 프로젝트의 승인 요청이 제출되었습니다. "
                        "관리자 승인 후 활성화됩니다.",
                    )
                    return redirect("projects:project_list")
```

Update the test:
```python
    @pytest.mark.django_db
    def test_create_with_high_collision(self, auth_consultant, client_obj, existing_project, user_consultant):
        resp = auth_consultant.post("/projects/new/", {
            "client": str(client_obj.pk),
            "title": "품질기획파트장",
            "jd_source": "",
        })
        assert resp.status_code == 302  # PRG redirect
        project = Project.objects.get(title="품질기획파트장")
        assert project.status == "pending_approval"
        approval = ProjectApproval.objects.get(project=project)
        assert approval.conflict_project == existing_project
        assert approval.conflict_score >= 0.7
```

**Additional test — medium collision non-blocking (Fix from I-R1-11):**

```python
    @pytest.mark.django_db
    def test_create_with_medium_collision_not_blocked(self, auth_consultant, client_obj, existing_project):
        """Medium collision (< 0.7) should NOT block creation."""
        resp = auth_consultant.post("/projects/new/", {
            "client": str(client_obj.pk),
            "title": "마케팅매니저",  # Low similarity with "품질기획팀장"
            "jd_source": "",
        })
        assert resp.status_code == 302
        project = Project.objects.get(title="마케팅매니저")
        assert project.status == "new"  # Not blocked
        assert not ProjectApproval.objects.filter(project=project).exists()
```

---

### Task 6: Views — Approval queue + decide + cancel + ALL pending_approval guards

Follow the original plan (debate/impl-plan.md Task 6) with these additions:

**Files:**
- Modify: `projects/views.py`
- Modify: `projects/urls.py`
- Create: `projects/templates/projects/approval_queue.html`
- Create: `projects/templates/projects/partials/approval_card.html`
- Test: `tests/test_p11_collision_approval.py` (append)

**Addition — Guard project_update and project_delete (Fixes 2, 3):**

Add `pending_approval` guard to `project_update` and `project_delete` views:

```python
@login_required
def project_update(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)
    # ... rest of existing code ...
```

```python
@login_required
def project_delete(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)
    # ... rest of existing code ...
```

Additional tests:
```python
class TestPendingApprovalGuards:
    # ... existing tests from original plan ...

    @pytest.mark.django_db
    def test_project_update_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.post(f"/projects/{pending_project.pk}/edit/", {
            "client": str(pending_project.client_id),
            "title": "수정된 제목",
        })
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_project_delete_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.post(f"/projects/{pending_project.pk}/delete/")
        assert resp.status_code == 403
        assert Project.objects.filter(pk=pending_project.pk).exists()
```

**Addition — Message action in UI (Fix 4):**

In `approval_card.html`, add message section:

```html
  <!-- Message section -->
  <div class="flex items-start gap-2 mt-2">
    <input type="text" name="response_text" placeholder="메시지를 입력하세요..."
           class="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-[14px] focus:ring-2 focus:ring-primary"
           form="decide-form-{{ approval.pk }}">
    <button type="submit" name="decision" value="메시지" form="decide-form-{{ approval.pk }}"
            class="px-4 py-2 bg-gray-600 text-white rounded-lg text-[14px] font-medium hover:bg-gray-700 transition">
      메시지
    </button>
  </div>
```

Additional test:
```python
    @pytest.mark.django_db
    def test_message_decision(self, auth_owner, approval, pending_project):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "메시지", "response_text": "추가 정보 필요합니다."},
        )
        assert resp.status_code == 302
        approval.refresh_from_db()
        assert approval.status == "대기"  # Unchanged
        assert approval.admin_response == "추가 정보 필요합니다."
```

**Addition — merge_target dropdown (Fix 5):**

In `approval_queue` view, pass merge target candidates:

```python
    # For each approval, compute merge target candidates
    for appr in approvals:
        appr.merge_candidates = Project.objects.filter(
            client=appr.project.client if appr.project else None,
            organization=org,
        ).exclude(
            status__in=["closed_success", "closed_fail", "closed_cancel", "pending_approval"],
        ).exclude(
            pk=appr.project_id,
        ) if appr.project else Project.objects.none()
```

In `approval_card.html`, add merge target select inside the form:

```html
    {% if approval.merge_candidates.exists %}
    <select name="merge_target" class="border border-gray-300 rounded-lg px-2 py-1.5 text-[13px]">
      <option value="">합류 대상: {{ approval.conflict_project.title|default:"자동 선택" }}</option>
      {% for candidate in approval.merge_candidates %}
      <option value="{{ candidate.pk }}" {% if candidate.pk == approval.conflict_project_id %}selected{% endif %}>
        {{ candidate.title }} ({{ candidate.get_status_display }})
      </option>
      {% endfor %}
    </select>
    {% endif %}
```

Additional test:
```python
    @pytest.mark.django_db
    def test_merge_with_custom_target(self, auth_owner, approval, pending_project, org, client_obj, user_consultant):
        alt_project = Project.objects.create(
            client=client_obj,
            organization=org,
            title="대체합류대상",
            status="searching",
            created_by=user_consultant,
        )
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "합류", "merge_target": str(alt_project.pk)},
        )
        assert resp.status_code == 302
        assert alt_project.assigned_consultants.filter(pk=user_consultant.pk).exists()
```

---

### Task 7: Project list — Pending approval UI

**Files:**
- Modify: `projects/templates/projects/partials/view_board_card.html`
- Modify: `projects/templates/projects/partials/view_list.html`
- Modify: `projects/templates/projects/partials/view_table.html`

- [ ] **Step 1: Add pending_approval badge and cancel button to board card**

In `view_board_card.html`, after the status display, add:

```html
{% if project.status == "pending_approval" %}
<div class="flex items-center gap-2 mt-1">
  <span class="inline-flex items-center px-2 py-0.5 rounded text-[12px] font-medium bg-yellow-100 text-yellow-800">
    승인 대기중
  </span>
  <form method="post" action="{% url 'projects:approval_cancel' pk=project.pk %}" class="inline">
    {% csrf_token %}
    <button type="submit" class="text-[12px] text-red-500 hover:text-red-700 underline"
            onclick="return confirm('승인 요청을 취소하시겠습니까?')">취소</button>
  </form>
</div>
{% endif %}
```

- [ ] **Step 2: Add same pattern to view_list.html and view_table.html**

Apply the same pending badge + cancel button pattern.

- [ ] **Step 3: Commit**

```bash
git add projects/templates/projects/partials/view_board_card.html projects/templates/projects/partials/view_list.html projects/templates/projects/partials/view_table.html
git commit -m "feat(p11): add pending approval badge and cancel button to project list views"
```

---

### Task 8: Sidebar badge for OWNER

**Files:**
- Create: `projects/context_processors.py`
- Modify: `main/settings.py`
- Modify: `templates/common/nav_sidebar.html`

- [ ] **Step 1: Create context processor**

Create `projects/context_processors.py`:

```python
"""Context processors for projects app."""

from projects.models import ProjectApproval


def pending_approval_count(request):
    """Inject pending approval count for OWNER users."""
    if not request.user.is_authenticated:
        return {}

    try:
        membership = request.user.membership
    except Exception:
        return {}

    if membership.role != "owner":
        return {}

    count = ProjectApproval.objects.filter(
        project__organization=membership.organization,
        status=ProjectApproval.Status.PENDING,
    ).count()

    return {"pending_approval_count": count}
```

- [ ] **Step 2: Register in settings**

In `main/settings.py`, add to `TEMPLATES[0]["OPTIONS"]["context_processors"]`:

```python
"projects.context_processors.pending_approval_count",
```

- [ ] **Step 3: Add badge to sidebar**

In `templates/common/nav_sidebar.html`, add approval queue link with badge for OWNER:

```html
{% if pending_approval_count is not None and pending_approval_count > 0 %}
<a href="{% url 'projects:approval_queue' %}"
   hx-get="{% url 'projects:approval_queue' %}" hx-target="#main-content" hx-push-url="true"
   class="flex items-center justify-between px-3 py-2 rounded-lg text-[15px] hover:bg-gray-100 transition">
  <span>승인 요청</span>
  <span class="bg-red-500 text-white text-[12px] font-bold rounded-full px-2 py-0.5">{{ pending_approval_count }}</span>
</a>
{% endif %}
```

- [ ] **Step 4: Commit**

```bash
git add projects/context_processors.py main/settings.py templates/common/nav_sidebar.html
git commit -m "feat(p11): add OWNER sidebar badge for pending approval count"
```

---

### Task 9: Regression fix + full test run

**Files:**
- Modify: `tests/test_projects_views.py`
- Test: All tests

- [ ] **Step 1: Run full test suite to identify regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: Identify failures from `status` field removal in `ProjectForm`

- [ ] **Step 2: Fix regressions in test_projects_views.py**

For any test that:
- POSTs `"status": "new"` or any status value when creating/editing a project — remove it
- Tests that the ProjectForm contains a `status` field — update or remove those assertions
- Tests edit functionality that sets status via form — update to use direct model update or `status_update` PATCH endpoint instead

- [ ] **Step 3: Run full suite again**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "fix(p11): fix test regressions from ProjectForm status field removal"
```

---

### Task 10: Lint and format

- [ ] **Step 1: Run ruff**

```bash
uv run ruff check projects/ tests/test_p11_collision_approval.py --fix
uv run ruff format projects/ tests/test_p11_collision_approval.py
```

- [ ] **Step 2: Migration check**

```bash
uv run python manage.py makemigrations --check --dry-run
```
Expected: "No changes detected"

- [ ] **Step 3: Final commit if needed**

```bash
git add -u
git commit -m "style(p11): apply ruff formatting"
```

<!-- forge:p11:구현담금질:complete:2026-04-09T00:00:00+09:00 -->
