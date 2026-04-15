# Task 8: 프로젝트 생성 시 담당 컨설턴트 지정 (확정 구현계획서)

**Goal:** 프로젝트 생성/수정 폼에 담당 컨설턴트 선택 필드를 추가하고, 미선택 시 생성자를 기본 담당자로 지정한다.

**Design spec:** `docs/forge/headhunting-onboarding/t08/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 5 (구현 완료), Task 6 (구현 완료)

**Permission note:** `project_create`는 `@membership_required`를 유지한다 (t05 ruling I-R1-01에 의해 owner-only가 아님). 설계서의 "owner만 가능" 전제는 t05 결정에 의해 오버라이드됨.

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/forms.py` | 수정 | ProjectForm에 assigned_consultants 필드 추가 |
| `projects/views.py` | 수정 | project_create: form.save_m2m() + 기본 담당자 로직, project_update: organization 전달 |
| `tests/accounts/test_rbac.py` | 수정 | 컨설턴트 지정 테스트 6건 추가 |

---

- [ ] **Step 1: Write failing tests**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestProjectConsultantAssignment:
    def test_owner_can_assign_consultants_on_create(self):
        """Owner selects specific consultants during project creation."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_a8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con = User.objects.create_user(username="con_a8", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8", organization=org)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Assigned Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "assigned_consultants": [str(con.pk)],
        }, follow=True)
        assert response.status_code == 200
        project = Project.objects.get(title="Assigned Project")
        assert con in project.assigned_consultants.all()
        # Owner should NOT be auto-added when explicit selection exists
        assert project.assigned_consultants.count() == 1

    def test_no_consultants_defaults_to_creator(self):
        """No consultants selected => creator becomes default assignee."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_b8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Co8b", organization=org)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Solo Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        assert response.status_code == 200
        project = Project.objects.get(title="Solo Project")
        assert owner in project.assigned_consultants.all()

    def test_consultant_can_create_with_self_assigned(self):
        """Consultant creates project (via approval workflow) and gets default assignment."""
        org = Organization.objects.create(name="Org")
        con = User.objects.create_user(username="con_c8", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8c", organization=org)

        test_client = TestClient()
        test_client.force_login(con)

        response = test_client.post("/projects/new/", {
            "title": "Consultant Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        assert response.status_code == 200
        project = Project.objects.get(title="Consultant Project")
        assert con in project.assigned_consultants.all()

    def test_update_changes_assigned_consultants(self):
        """Owner can change assigned consultants on update."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_d8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con1 = User.objects.create_user(username="con_d8a", password="p")
        Membership.objects.create(
            user=con1, organization=org, role="consultant", status="active"
        )
        con2 = User.objects.create_user(username="con_d8b", password="p")
        Membership.objects.create(
            user=con2, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8d", organization=org)
        project = Project.objects.create(
            title="Update Test",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        project.assigned_consultants.add(con1)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post(f"/projects/{project.pk}/edit/", {
            "title": "Update Test",
            "client": str(client_co.pk),
            "jd_text": "Updated JD",
            "assigned_consultants": [str(con2.pk)],
        }, follow=True)
        assert response.status_code == 200
        project.refresh_from_db()
        assert con2 in project.assigned_consultants.all()
        assert con1 not in project.assigned_consultants.all()

    def test_cross_org_user_rejected_on_create(self):
        """Submitting a user PK from another org is rejected by form validation."""
        org1 = Organization.objects.create(name="Org1")
        org2 = Organization.objects.create(name="Org2")
        owner = User.objects.create_user(username="own_e8", password="p")
        Membership.objects.create(
            user=owner, organization=org1, role="owner", status="active"
        )
        alien = User.objects.create_user(username="alien_e8", password="p")
        Membership.objects.create(
            user=alien, organization=org2, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8e", organization=org1)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Cross Org Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "assigned_consultants": [str(alien.pk)],
        })
        # Form should be invalid — cross-org PK not in queryset
        assert not Project.objects.filter(title="Cross Org Project").exists()

    def test_update_can_clear_all_consultants(self):
        """Clearing all consultants on update is allowed (no default fallback)."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_f8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con = User.objects.create_user(username="con_f8", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8f", organization=org)
        project = Project.objects.create(
            title="Clear Test",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        project.assigned_consultants.add(con)

        test_client = TestClient()
        test_client.force_login(owner)

        # POST without assigned_consultants field => M2M cleared
        response = test_client.post(f"/projects/{project.pk}/edit/", {
            "title": "Clear Test",
            "client": str(client_co.pk),
            "jd_text": "Updated JD",
        }, follow=True)
        assert response.status_code == 200
        project.refresh_from_db()
        assert project.assigned_consultants.count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: FAIL (assigned_consultants field not yet in form)

- [ ] **Step 3: Add assigned_consultants field to ProjectForm**

In `projects/forms.py`, modify `ProjectForm`:

1. Add `User` import at top:
```python
from django.contrib.auth import get_user_model
User = get_user_model()
```

2. Add field to `ProjectForm` class body (after Meta class, before `__init__`):
```python
assigned_consultants = forms.ModelMultipleChoiceField(
    queryset=User.objects.none(),
    required=False,
    widget=forms.CheckboxSelectMultiple,
    label="담당 컨설턴트",
)
```

3. In existing `__init__` (which uses `organization=None`), add after the client queryset filter:
```python
if organization:
    self.fields["client"].queryset = Client.objects.filter(
        organization=organization
    )
    self.fields["assigned_consultants"].queryset = User.objects.filter(
        membership__organization=organization,
        membership__status="active",
    )
```

**Note:** `distinct()` is unnecessary because `Membership.user` is a `OneToOneField` — each user has at most one membership.

- [ ] **Step 4: Update project_create view**

In `projects/views.py`, within `project_create`, modify the save logic in **both branches** of the collision check. The key changes:

**In the `high_collisions` branch (line ~267-268):**
Replace:
```python
project.save()
project.assigned_consultants.add(request.user)
```
With:
```python
project.save()
form.save_m2m()
if not project.assigned_consultants.exists():
    project.assigned_consultants.add(request.user)
```

**In the `else` (no collision) branch (line ~332-333):**
Replace:
```python
project.save()
project.assigned_consultants.add(request.user)
```
With:
```python
project.save()
form.save_m2m()
if not project.assigned_consultants.exists():
    project.assigned_consultants.add(request.user)
```

All other code in `project_create` (collision detection, ProjectApproval creation, Telegram notifications, redirects) remains unchanged.

- [ ] **Step 4.5: Update project_update view**

In `projects/views.py`, within `project_update`, no special handling needed beyond what `form.save()` already does. Since `project_update` uses `form.save()` (not `commit=False`), Django will automatically save M2M relations including `assigned_consultants`. The form already receives `organization=org`, which will filter the queryset.

No default fallback on update — clearing all consultants is allowed.

Verify that the form instantiation already passes `organization=org` (it does: `ProjectForm(request.POST, request.FILES, instance=project, organization=org)` at line 387 and `ProjectForm(instance=project, organization=org)` at line 393).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: All 6 tests PASS

Run: `uv run pytest -v`
Expected: All existing tests still PASS (no regression in collision/approval flow)

- [ ] **Step 6: Commit**

```bash
git add projects/forms.py projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): add consultant assignment on project create/update"
```

---

## Tempering Rulings Applied

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| I-R1-01 | CRITICAL | Parameter name mismatch (org vs organization) | ACCEPTED — Use `organization=` throughout |
| I-R1-02 | CRITICAL | Step 4 overwrites collision workflow + M2M conflict | ACCEPTED — Preserve both branches, call form.save_m2m(), add default fallback |
| I-R1-03 | MAJOR | Update view missing from plan | ACCEPTED — Added Step 4.5, no default fallback on update |
| I-R1-04 | MAJOR | Permission premise conflict | ACCEPTED — @membership_required unchanged per t05 |
| I-R1-05 | MAJOR | Tests too narrow scope | PARTIAL — Expanded to 6 test cases |
| I-R1-06 | MAJOR | No negative security tests | ACCEPTED — Added cross-org PK rejection test |
| I-R1-07 | MINOR | CheckboxSelectMultiple scalability | REBUTTED — Current scale acceptable |

<!-- forge:t08:구현담금질:complete:2026-04-12T10:30:00+09:00 -->
