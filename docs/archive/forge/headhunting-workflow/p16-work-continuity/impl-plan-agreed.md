# P16: Work Continuity — 확정 구현계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add work continuity (autosave/resume of form state) and event-triggered auto-actions (posting drafts, candidate search, reminders) to the projects app.

**Architecture:** Two subsystems: (1) ProjectContext autosave/resume using a unique-per-consultant context row with three-tier JS save (periodic fetch, fetch+keepalive on unload, HTMX event), and (2) AutoAction model with Django signals creating lightweight pending records on model state transitions, plus a management command for time-based triggers. AI generation is lazy (on user demand), not in signals.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, PostgreSQL (UUID PKs, BaseModel), pytest-django

**Base plan:** `debate/impl-plan.md` with amendments below applied. Read the base plan first, then apply all amendments.

---

## Amendments to Base Plan

The following amendments MUST be applied when implementing the base plan. Each amendment references the specific Task and location in the base plan.

### Amendment A1: Fix conftest project fixture (Task 1)

In `tests/conftest.py`, change the `project` fixture to use `SEARCHING` status instead of `NEW`, to prevent signal-triggered AutoAction pollution in non-signal tests.

```python
@pytest.fixture
def project(db, org, client_company, user):
    return Project.objects.create(
        client=client_company,
        organization=org,
        title="품질기획",
        status=ProjectStatus.SEARCHING,   # NOT NEW — avoids signal trigger
        created_by=user,
    )
```

Add a separate fixture for signal tests:

```python
@pytest.fixture
def new_project(db, org, client_company, user):
    """Project with NEW status — triggers on_project_created signal."""
    return Project.objects.create(
        client=client_company,
        organization=org,
        title="Signal Test Project",
        status=ProjectStatus.NEW,
        created_by=user,
    )
```

Signal tests (Task 5) should use `new_project` fixture or create projects inline with `ProjectStatus.NEW`.

### Amendment A2: Add data migration for ProjectContext dedup (Task 2)

Before the migration that adds `UniqueConstraint`, add a `RunPython` step:

```python
def deduplicate_contexts(apps, schema_editor):
    ProjectContext = apps.get_model("projects", "ProjectContext")
    from django.db.models import Max
    
    # Find duplicates
    dupes = (
        ProjectContext.objects.values("project_id", "consultant_id")
        .annotate(max_id=Max("id"), cnt=models.Count("id"))
        .filter(cnt__gt=1)
    )
    for dupe in dupes:
        # Keep the newest (by id since UUIDs are random, use updated_at)
        to_keep = (
            ProjectContext.objects.filter(
                project_id=dupe["project_id"],
                consultant_id=dupe["consultant_id"],
            )
            .order_by("-updated_at")
            .first()
        )
        ProjectContext.objects.filter(
            project_id=dupe["project_id"],
            consultant_id=dupe["consultant_id"],
        ).exclude(pk=to_keep.pk).delete()

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(deduplicate_contexts, migrations.RunPython.noop),
        # Then the AddConstraint operation
    ]
```

### Amendment A3: Fix signal idempotency — remove status filter (Task 5)

In ALL signal handlers, change idempotency checks to NOT filter by `status=ActionStatus.PENDING`. Any existing action (pending, applied, dismissed) blocks re-creation.

**Before (wrong):**
```python
if AutoAction.objects.filter(
    project=instance.project,
    action_type=ActionType.SUBMISSION_DRAFT,
    status=ActionStatus.PENDING,
    data__candidate_id=candidate_id,
).exists():
    return
```

**After (correct):**
```python
if AutoAction.objects.filter(
    project=instance.project,
    action_type=ActionType.SUBMISSION_DRAFT,
    data__candidate_id=candidate_id,
).exists():
    return
```

Apply this to ALL four signal handlers (Project, Contact, Submission, Interview).

### Amendment A4: Add type-specific dispatch to apply_action (Task 4)

Replace the `apply_action` function with a version that dispatches per ActionType:

```python
# projects/services/auto_actions.py

def apply_action(action_id, user) -> AutoAction:
    """Apply a pending action with type-specific dispatch. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatus.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")
        
        if not validate_action_data(action.action_type, action.data):
            raise ValidationError("액션 데이터가 유효하지 않습니다.")
        
        # Type-specific dispatch
        _APPLY_HANDLERS[action.action_type](action, user)
        
        action.status = ActionStatus.APPLIED
        action.applied_by = user
        action.save(update_fields=["status", "applied_by", "updated_at"])
    return action


class ValidationError(Exception):
    pass


def _apply_posting_draft(action, user):
    """Set project.posting_text from generated draft."""
    from projects.models import Project
    text = action.data.get("text", "")
    if text:
        Project.objects.filter(pk=action.project_id).update(posting_text=text)


def _apply_candidate_search(action, user):
    """Candidate search results stored in data; apply is acknowledgment only."""
    # The actual selection UI is handled in the view.
    # Apply just marks the search results as reviewed.
    pass


def _apply_submission_draft(action, user):
    """Create or update SubmissionDraft with auto_draft_json."""
    from projects.models import Submission, SubmissionDraft
    candidate_id = action.data.get("candidate_id")
    draft_json = action.data.get("draft_json", {})
    if not candidate_id or not draft_json:
        return
    submission = Submission.objects.filter(
        project=action.project,
        candidate_id=candidate_id,
    ).first()
    if submission:
        SubmissionDraft.objects.update_or_create(
            submission=submission,
            defaults={"auto_draft_json": draft_json},
        )


def _apply_offer_template(action, user):
    """Create Offer from template data."""
    from projects.models import Offer, Submission
    submission_id = action.data.get("submission_id")
    if not submission_id:
        return
    submission = Submission.objects.filter(pk=submission_id).first()
    if not submission:
        return
    if hasattr(submission, "offer"):
        return  # Already has offer, don't duplicate
    Offer.objects.create(
        submission=submission,
        salary=action.data.get("salary", ""),
        terms=action.data.get("terms", {}),
    )


def _apply_followup_reminder(action, user):
    """Create Notification for the consultant."""
    from projects.models import Notification
    Notification.objects.get_or_create(
        recipient=user,
        type=Notification.Type.REMINDER,
        title=action.title,
        callback_data={"auto_action_id": str(action.pk)},
        defaults={
            "body": action.data.get("message", action.title),
        },
    )


def _apply_recontact_reminder(action, user):
    """Create Notification for the consultant."""
    from projects.models import Notification
    Notification.objects.get_or_create(
        recipient=user,
        type=Notification.Type.REMINDER,
        title=action.title,
        callback_data={"auto_action_id": str(action.pk)},
        defaults={
            "body": action.data.get("message", action.title),
        },
    )


_APPLY_HANDLERS = {
    ActionType.POSTING_DRAFT: _apply_posting_draft,
    ActionType.CANDIDATE_SEARCH: _apply_candidate_search,
    ActionType.SUBMISSION_DRAFT: _apply_submission_draft,
    ActionType.OFFER_TEMPLATE: _apply_offer_template,
    ActionType.FOLLOWUP_REMINDER: _apply_followup_reminder,
    ActionType.RECONTACT_REMINDER: _apply_recontact_reminder,
}
```

### Amendment A5: Fix FORM_REGISTRY contact_update lookup (Task 3)

```python
"contact_update": {
    "url_name": "projects:contact_update",
    "url_kwargs": lambda ctx: {
        "pk": str(ctx.project_id),
        "contact_pk": ctx.draft_data.get("fields", {}).get("contact_id", ""),
    },
},
```

### Amendment A6: Fix validate_draft_data to use byte length (Task 3)

```python
def validate_draft_data(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if not REQUIRED_KEYS.issubset(data.keys()):
        return False
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_DRAFT_SIZE:
        return False
    return True
```

### Amendment A7: Fix autosave JS — use fetch+keepalive instead of sendBeacon (Task 8)

Replace the `beaconSave` function:

```javascript
// Tier 2: fetch with keepalive on unload (replaces sendBeacon)
function keepaliveSave() {
  if (!_dirty) return;
  var url = getSaveUrl();
  var payload = buildPayload();
  if (!url || !payload) return;

  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(function () {
    /* silent — page is unloading */
  });
}
```

And update the event listener:

```javascript
window.addEventListener("beforeunload", keepaliveSave);
// cleanup:
window.removeEventListener("beforeunload", keepaliveSave);
```

### Amendment A8: Add JS include and form annotations (Task 8/9)

Add to Task 8 or create a new step in Task 9:

1. Include the JS in the project detail template (or base template):

```html
<!-- In projects/project_detail.html or base template -->
<script src="{% static 'js/context-autosave.js' %}"></script>
```

2. Annotate the contact form with autosave attributes. In `projects/templates/projects/partials/contact_form.html`, add to the `<form>` tag:

```html
<form data-autosave="contact_create"
      data-autosave-action="{{ pending_action|default:'' }}"
      ...existing attributes...>
```

3. Add `data-project-pk` to a container element in `projects/project_detail.html`:

```html
<div data-project-pk="{{ project.pk }}">
  ...
</div>
```

### Amendment A9: Add resume pre-fill to contact_create view (New Task or Task 9 expansion)

Modify the existing `contact_create` view in `projects/views.py` to support resume:

```python
@login_required
def contact_create(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    
    # P16: Resume support
    initial = {}
    resume_id = request.GET.get("resume")
    if resume_id:
        from projects.services.context import get_active_context
        ctx = get_active_context(project, request.user)
        if ctx and str(ctx.pk) == resume_id:
            initial = ctx.draft_data.get("fields", {})
    
    if request.method == "POST":
        # ... existing POST handling ...
    else:
        form = ContactForm(initial=initial)  # Pass initial from resume
    
    # ... rest of existing logic ...
```

### Amendment A10: Fix management command — mark due actions applied (Task 7)

In `_process_due_actions`, after notification creation, mark the action applied:

```python
def _process_due_actions(self, now) -> int:
    due_actions = AutoAction.objects.filter(
        status=ActionStatus.PENDING,
        due_at__lte=now,
    ).select_related("project", "created_by")

    count = 0
    for action in due_actions:
        recipient = action.created_by or action.project.created_by
        if not recipient:
            continue

        _, created = Notification.objects.get_or_create(
            recipient=recipient,
            type=Notification.Type.REMINDER,
            callback_data__auto_action_id=str(action.pk),
            defaults={
                "title": action.title,
                "body": action.data.get("message", action.title),
                "callback_data": {"auto_action_id": str(action.pk)},
            },
        )
        # Mark the action as applied regardless
        action.status = ActionStatus.APPLIED
        action.save(update_fields=["status", "updated_at"])
        if created:
            count += 1
    return count
```

### Amendment A11: Fix management command idempotency — use get_or_create without JSON filter (Task 7)

Replace `get_or_create` with explicit `exists()` + `create()` in `_check_expiring_locks`:

```python
def _check_expiring_locks(self, now, tomorrow) -> int:
    expiring = Contact.objects.filter(
        result=Contact.Result.RESERVED,
        locked_until__lte=tomorrow,
        locked_until__gt=now,
    ).select_related("candidate", "project", "consultant")

    count = 0
    for contact in expiring:
        contact_id = str(contact.pk)
        if AutoAction.objects.filter(
            project=contact.project,
            action_type=ActionType.RECONTACT_REMINDER,
            data__contact_id=contact_id,
        ).exists():
            continue
        AutoAction.objects.create(
            project=contact.project,
            trigger_event="lock_expiring",
            action_type=ActionType.RECONTACT_REMINDER,
            title=f"{contact.candidate.name} 컨택 잠금 내일 만료",
            data={"contact_id": contact_id},
            created_by=contact.consultant,
        )
        count += 1
    return count
```

### Amendment A12: Add missing tests (Task 6 expansion)

Add these tests to `tests/test_context_views.py`:

```python
@pytest.mark.django_db
class TestContextResumeView:
    def test_resume_returns_hx_redirect(self, auth_client, project, user):
        from projects.models import ProjectContext
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="contact_create",
            draft_data={"form": "contact_create", "fields": {"channel": "phone"}},
        )
        url = f"/projects/{project.pk}/context/resume/"
        response = auth_client.post(url)
        assert response.status_code == 200
        assert "HX-Redirect" in response
        redirect_url = response["HX-Redirect"]
        assert f"/projects/{project.pk}/contacts/new/" in redirect_url
        assert "resume=" in redirect_url

    def test_resume_no_context_returns_404(self, auth_client, project):
        url = f"/projects/{project.pk}/context/resume/"
        response = auth_client.post(url)
        assert response.status_code == 404

    def test_resume_unknown_form_returns_404(self, auth_client, project, user):
        from projects.models import ProjectContext
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="unknown_form",
            draft_data={"form": "unknown_form"},
        )
        url = f"/projects/{project.pk}/context/resume/"
        response = auth_client.post(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestAutoActionPermissions:
    def test_other_org_cannot_list_actions(self, other_org_client, project):
        url = f"/projects/{project.pk}/auto-actions/"
        response = other_org_client.get(url)
        assert response.status_code == 404

    def test_other_org_cannot_apply_action(self, other_org_client, project):
        from projects.models import AutoAction, ActionType
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.POSTING_DRAFT,
            title="test",
            data={},
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/apply/"
        response = other_org_client.post(url)
        assert response.status_code == 404
```

### Amendment A13: Specify exact Task 9 view modification

Replace Task 9 Step 2 with this exact code change to `project_tab_overview`:

```python
@login_required
def project_tab_overview(request, pk):
    """개요: JD 요약, 퍼널, 담당자, 최근 진행 현황."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    context = _build_overview_context(project)
    context["project"] = project
    
    # P16: Work Continuity banners
    from projects.services.context import get_active_context, get_resume_url
    from projects.services.auto_actions import get_pending_actions
    ctx = get_active_context(project, request.user)
    context["context"] = ctx
    context["resume_url"] = get_resume_url(ctx) if ctx else None
    context["pending_actions"] = get_pending_actions(project)
    
    return render(request, "projects/partials/tab_overview.html", context)
```

### Amendment A14: Fix lint command order (Task 10)

```bash
uv run ruff check . --fix && uv run ruff format . && uv run ruff check .
```

---

## Task Execution Order (unchanged)

1. Shared test fixtures (with A1 amendment)
2. AutoAction model + ProjectContext constraint (with A2 amendment)
3. Context service (with A5, A6 amendments)
4. AutoAction service (with A4 amendment)
5. Django signals (with A3 amendment)
6. Views + URLs (with A12 amendment)
7. Management command (with A10, A11 amendments)
8. Autosave JS (with A7, A8 amendments)
9. Integrate banners (with A9, A13 amendments)
10. Lint + final verification (with A14 amendment)

<!-- forge:p16-work-continuity:구현담금질:complete:2026-04-10T16:10:00Z -->
