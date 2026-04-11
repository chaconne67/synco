# Task 5: 기존 view에 권한 데코레이터 적용 (확정 구현계획서)

**Goal:** 모든 client/project view에 `membership_required` 또는 `role_required("owner")` 데코레이터를 적용하여 역할 기반 접근 제어를 실현한다.

**Design spec:** `docs/forge/headhunting-onboarding/t05/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 4 (구현 완료)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `clients/views.py` | 수정 | client/contract views에 데코레이터 추가 |
| `clients/views_reference.py` | 수정 | reference 읽기 views에 `@membership_required` 추가 |
| `projects/views.py` | 수정 | owner-only + membership_required 데코레이터 추가, 인라인 체크 제거 |
| `tests/accounts/test_rbac.py` | 수정 | 통합 테스트 추가 |

---

- [ ] **Step 1: Write failing integration tests**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestViewPermissions:
    """Route-level integration tests for RBAC decorators."""

    def test_consultant_cannot_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 403

    def test_owner_can_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 200

    def test_consultant_cannot_create_project(self):
        """Consultant CAN access project_create (approval workflow needs it)."""
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con2", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/projects/new/")
        # project_create uses @membership_required (not owner-only)
        # because P11 approval workflow requires consultant access
        assert response.status_code == 200

    def test_consultant_can_read_client_list(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con3", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/")
        assert response.status_code == 200

    def test_consultant_cannot_delete_project(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con4", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.post("/projects/delete-nonexistent/")
        # Even before 404, role_required should return 403
        assert response.status_code == 403

    def test_consultant_cannot_access_approval_queue(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con5", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/approvals/")
        assert response.status_code == 403

    def test_no_membership_redirects_to_invite(self):
        user = User.objects.create_user(username="nomem", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/")
        assert response.status_code == 302
        assert "/accounts/invite/" in response.url

    def test_consultant_cannot_access_dashboard_team(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con6", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/dashboard/team/")
        assert response.status_code == 403

    def test_consultant_can_access_dashboard_actions(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con7", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/dashboard/actions/")
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/accounts/test_rbac.py::TestViewPermissions -v`
Expected: Several tests FAIL (consultant can currently access owner-only views)

- [ ] **Step 3: Apply decorators to clients/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Apply decorators (after `@login_required`):

| View | Decorator |
|------|-----------|
| `client_list` | `@membership_required` |
| `client_create` | `@role_required("owner")` |
| `client_detail` | `@membership_required` |
| `client_update` | `@role_required("owner")` |
| `client_delete` | `@role_required("owner")` |
| `contract_create` | `@role_required("owner")` |
| `contract_update` | `@role_required("owner")` |
| `contract_delete` | `@role_required("owner")` |

- [ ] **Step 4: Apply @membership_required to reference read views in clients/views_reference.py**

Add import at top:

```python
from accounts.decorators import membership_required
```

Apply `@membership_required` to read-only views (after `@login_required`):

| View | Decorator |
|------|-----------|
| `reference_index` | `@membership_required` |
| `reference_universities` | `@membership_required` |
| `reference_companies` | `@membership_required` |
| `reference_certs` | `@membership_required` |
| `university_export` | `@membership_required` |
| `company_export` | `@membership_required` |
| `cert_export` | `@membership_required` |

**Note:** Write views keep existing `@staff_member_required` (staff→role 전환은 별도 작업).

- [ ] **Step 5: Apply decorators to projects/views.py**

Import already exists (`from accounts.decorators import membership_required`). Add `role_required`:

```python
from accounts.decorators import membership_required, role_required
```

### Owner-only views (`@role_required("owner")`):

| View | Decorator |
|------|-----------|
| `project_delete` | `@role_required("owner")` |
| `approval_queue` | `@role_required("owner")` + **remove inline `_is_owner()` check** |
| `approval_decide` | `@role_required("owner")` + **remove inline `_is_owner()` check** |
| `dashboard_team` | `@role_required("owner")` + **remove inline `is_owner` check** |

### Membership-required views (`@membership_required`):

| View | Decorator |
|------|-----------|
| `project_list` | `@membership_required` |
| `status_update` | `@membership_required` |
| `project_check_collision` | `@membership_required` |
| `project_create` | `@membership_required` (**NOT owner-only** -- P11 approval workflow) |
| `project_detail` | `@membership_required` |
| `project_update` | `@membership_required` |
| `project_tab_overview` | `@membership_required` |
| `project_tab_search` | `@membership_required` |
| `project_tab_contacts` | `@membership_required` |
| `project_tab_submissions` | `@membership_required` |
| `project_tab_interviews` | `@membership_required` |
| `project_tab_offers` | `@membership_required` |
| `analyze_jd` | `@membership_required` |
| `jd_results` | `@membership_required` |
| `drive_picker` | `@membership_required` |
| `start_search_session` | `@membership_required` |
| `jd_matching_results` | `@membership_required` |
| `contact_create` | `@membership_required` |
| `contact_update` | `@membership_required` |
| `contact_delete` | `@membership_required` |
| `contact_reserve` | `@membership_required` |
| `contact_release_lock` | `@membership_required` |
| `contact_check_duplicate` | `@membership_required` |
| `submission_create` | `@membership_required` |
| `submission_update` | `@membership_required` |
| `submission_delete` | `@membership_required` |
| `submission_submit` | `@membership_required` |
| `submission_feedback` | `@membership_required` |
| `submission_download` | `@membership_required` |
| `submission_draft` | `@membership_required` |
| `draft_generate` | `@membership_required` |
| `draft_consultation` | `@membership_required` |
| `draft_consultation_audio` | `@membership_required` |
| `draft_finalize` | `@membership_required` |
| `draft_review` | `@membership_required` |
| `draft_convert` | `@membership_required` |
| `draft_preview` | `@membership_required` |
| `interview_create` | `@membership_required` |
| `interview_update` | `@membership_required` |
| `interview_delete` | `@membership_required` |
| `interview_result` | `@membership_required` |
| `offer_create` | `@membership_required` |
| `offer_update` | `@membership_required` |
| `offer_delete` | `@membership_required` |
| `offer_accept` | `@membership_required` |
| `offer_reject` | `@membership_required` |
| `posting_generate` | `@membership_required` |
| `posting_edit` | `@membership_required` |
| `posting_download` | `@membership_required` |
| `posting_sites` | `@membership_required` |
| `posting_site_add` | `@membership_required` |
| `posting_site_update` | `@membership_required` |
| `posting_site_delete` | `@membership_required` |
| `approval_cancel` | `@membership_required` |
| `dashboard_actions` | `@membership_required` |
| `project_context` | `@membership_required` |
| `project_context_save` | `@membership_required` |
| `project_context_resume` | `@membership_required` |
| `project_context_discard` | `@membership_required` |
| `project_auto_actions` | `@membership_required` |
| `auto_action_apply` | `@membership_required` |
| `auto_action_dismiss` | `@membership_required` |
| `resume_upload` | `@membership_required` |
| `resume_process_pending` | `@membership_required` |
| `resume_upload_status` | `@membership_required` |
| `resume_link_candidate` | `@membership_required` |
| `resume_discard` | `@membership_required` |
| `resume_retry` | `@membership_required` |
| `resume_unassigned` | `@membership_required` |
| `resume_assign_project` | `@membership_required` |

### Already decorated (no change):

| View | Current Decorator |
|------|-----------|
| `dashboard` | `@membership_required` (applied in t04) |

### Inline code removal in owner-only views:

**approval_queue:** Remove `if not _is_owner(request): return HttpResponse(status=403)` block (lines ~2230-2231).

**approval_decide:** Remove `if not _is_owner(request): return HttpResponse(status=403)` block.

**dashboard_team:** Remove `is_owner = False; try: is_owner = ... except: pass; if not is_owner: return HttpResponse(status=403)` block (lines ~2418-2425).

**Note:** `_is_owner()` helper function itself is kept -- it may be used elsewhere for template context.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_rbac.py -v`
Expected: All tests PASS

Run: `uv run pytest -v`
Expected: All existing tests still PASS

- [ ] **Step 7: Commit**

```bash
git add clients/views.py clients/views_reference.py projects/views.py tests/accounts/test_rbac.py
git commit -m "feat: apply RBAC decorators to all client and project views"
```

---

## Tempering Rulings Applied

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| I-R1-01 | CRITICAL | project_create owner-only breaks approval workflow | ACCEPTED -- Changed to @membership_required |
| I-R1-02 | MAJOR | Reference views file path + staff_member_required conflict | PARTIAL -- Added views_reference.py to File Map, read views get @membership_required, write views keep @staff_member_required |
| I-R1-03 | MAJOR | membership_required insufficient for project assignment filter | REBUTTED -- t06 scope |
| I-R1-04 | MAJOR | dashboard_actions/dashboard_team missing | ACCEPTED -- Added to Step 5 |
| I-R1-05 | MAJOR | Inline _is_owner() cleanup | ACCEPTED -- Remove inline checks when applying @role_required |
| I-R1-06 | MAJOR | --timeout=30 unavailable | ACCEPTED -- Changed to uv run pytest -v |
| I-R1-07 | MAJOR | Integration test coverage insufficient | PARTIAL -- Added 9 route-level tests covering key permission boundaries |
| I-R1-08 | MINOR | "All remaining views" ambiguous | ACCEPTED -- Full view list enumerated |

<!-- forge:t05:구현담금질:complete:2026-04-12T08:30:00+09:00 -->
