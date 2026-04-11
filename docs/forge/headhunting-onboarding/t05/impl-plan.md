# Task 5: 기존 view에 권한 데코레이터 적용

**Goal:** 모든 client/project view에 `membership_required` 또는 `role_required("owner")` 데코레이터를 적용하여 역할 기반 접근 제어를 실현한다.

**Design spec:** `docs/forge/headhunting-onboarding/t05/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 4

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | owner-only views에 `@role_required("owner")` 추가 |
| `clients/views.py` | 수정 | create/update/delete에 `@role_required("owner")` 추가 |
| `tests/accounts/test_rbac.py` | 수정 | 기존 파일에 통합 테스트 추가 |

---

- [ ] **Step 1: Write failing integration test**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestViewPermissions:
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
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con2", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/projects/new/")
        assert response.status_code == 403

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestViewPermissions -v`
Expected: FAIL -- consultant can currently access all views (200 instead of 403)

- [ ] **Step 3: Apply role_required to clients/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Add `@membership_required` to all views. Add `@role_required("owner")` to write views:

```python
# client_list -- all roles can read
@login_required
@membership_required
def client_list(request):
    ...

# client_create -- owner only
@login_required
@role_required("owner")
def client_create(request):
    ...

# client_detail -- all roles can read
@login_required
@membership_required
def client_detail(request, pk):
    ...

# client_update -- owner only
@login_required
@role_required("owner")
def client_update(request, pk):
    ...

# client_delete -- owner only
@login_required
@role_required("owner")
def client_delete(request, pk):
    ...

# contract_create -- owner only
@login_required
@role_required("owner")
def contract_create(request, pk):
    ...

# contract_update -- owner only
@login_required
@role_required("owner")
def contract_update(request, pk, contract_pk):
    ...

# contract_delete -- owner only
@login_required
@role_required("owner")
def contract_delete(request, pk, contract_pk):
    ...
```

Apply `@role_required("owner")` to all reference views in `clients/views.py` (university/company/cert CRUD, import, export, autofill) -- these are accessed via `/reference/` URLs defined in `clients/urls_reference.py`.

- [ ] **Step 4: Apply role_required to projects/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Apply to owner-only views:

```python
# project_create -- owner only
@login_required
@role_required("owner")
def project_create(request):
    ...

# project_delete -- owner only
@login_required
@role_required("owner")
def project_delete(request, pk):
    ...

# approval_queue -- owner only
@login_required
@role_required("owner")
def approval_queue(request):
    ...

# approval_decide -- owner only
@login_required
@role_required("owner")
def approval_decide(request, appr_pk):
    ...
```

Apply `@membership_required` to all remaining views (project_list, project_detail, all tab views, all CRUD views). The `@membership_required` goes after `@login_required` on every view function.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_rbac.py -v`
Expected: All tests PASS

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add projects/views.py clients/views.py tests/accounts/test_rbac.py
git commit -m "feat: apply RBAC decorators to all client and project views"
```
