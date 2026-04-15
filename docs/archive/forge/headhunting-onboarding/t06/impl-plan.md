# Task 6: 프로젝트 목록 consultant 필터링

**Goal:** 프로젝트 목록 view에서 consultant는 배정된 프로젝트만, owner는 전체 프로젝트를 보도록 역할별 queryset 필터링을 적용한다.

**Design spec:** `docs/forge/headhunting-onboarding/t06/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 5

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py:78-170` | 수정 | project_list queryset 역할별 분기 |
| `tests/accounts/test_rbac.py` | 수정 | 프로젝트 필터링 테스트 추가 |

---

- [ ] **Step 1: Write failing test**

Append to `tests/accounts/test_rbac.py`:

```python
from clients.models import Client
from projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestProjectFiltering:
    def test_consultant_sees_only_assigned_projects(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="owner", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        consultant = User.objects.create_user(username="con", password="p")
        Membership.objects.create(
            user=consultant, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        # Project assigned to consultant
        p1 = Project.objects.create(
            title="Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        p1.assigned_consultants.add(consultant)

        # Project NOT assigned to consultant
        Project.objects.create(
            title="Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = TestClient()
        test_client.force_login(consultant)

        response = test_client.get("/projects/")
        content = response.content.decode()
        assert "Assigned" in content
        assert "Not Assigned" not in content

    def test_owner_sees_all_projects(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="owner2", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        Project.objects.create(
            title="Project1",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.get("/projects/")
        content = response.content.decode()
        assert "Project1" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: FAIL -- consultant currently sees all projects

- [ ] **Step 3: Modify project_list to filter by role**

In `projects/views.py`, within the `project_list` function, after `org = _get_org(request)`, add role-based filtering:

```python
@login_required
@membership_required
def project_list(request):
    org = _get_org(request)

    # Role-based filtering
    membership = request.user.membership
    if membership.role == "owner":
        qs = Project.objects.filter(organization=org)
    else:
        qs = Project.objects.filter(
            organization=org, assigned_consultants=request.user
        )

    # ... rest of existing filter/sort logic uses qs instead of Project.objects.filter(organization=org)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: All tests PASS

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): filter project list by consultant assignment"
```
