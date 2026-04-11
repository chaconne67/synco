# Task 6: 프로젝트 목록 consultant 필터링 (확정 구현계획서)

**Goal:** 프로젝트 목록 view에서 consultant/viewer는 배정된 프로젝트만, owner는 전체 프로젝트를 보도록 역할별 queryset 필터링을 적용한다.

**Design spec:** `docs/forge/headhunting-onboarding/t06/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 5 (구현 완료)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py:84` | 수정 | project_list queryset 역할별 분기 |
| `tests/accounts/test_rbac.py` | 수정 | 프로젝트 필터링 테스트 추가 |

---

- [ ] **Step 1: Write failing test**

Append to `tests/accounts/test_rbac.py`:

```python
from clients.models import Client
from projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestProjectFiltering:
    @pytest.mark.parametrize("role", ["consultant", "viewer"])
    def test_non_owner_sees_only_assigned_projects(self, role):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username=f"owner_{role}", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        user = User.objects.create_user(username=f"user_{role}", password="p")
        Membership.objects.create(
            user=user, organization=org, role=role, status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        # Project assigned to user
        p1 = Project.objects.create(
            title="Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        p1.assigned_consultants.add(user)

        # Project NOT assigned but created_by user (should NOT be visible)
        Project.objects.create(
            title="Created But Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )

        # Project NOT assigned at all
        Project.objects.create(
            title="Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = TestClient()
        test_client.force_login(user)

        # Test with scope=all (the real behavioral change)
        response = test_client.get("/projects/?scope=all")
        content = response.content.decode()
        assert "Assigned" in content
        assert "Created But Not Assigned" not in content
        assert "Not Assigned" not in content

    def test_owner_sees_all_projects(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="owner2", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        other = User.objects.create_user(username="other2", password="p")
        Membership.objects.create(
            user=other, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        # Project created by owner
        Project.objects.create(
            title="Owner Project",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        # Project created by another user, assigned to another user
        p2 = Project.objects.create(
            title="Other Project",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=other,
        )
        p2.assigned_consultants.add(other)

        test_client = TestClient()
        test_client.force_login(owner)

        # Owner should see all projects with scope=all
        response = test_client.get("/projects/?scope=all")
        content = response.content.decode()
        assert "Owner Project" in content
        assert "Other Project" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: FAIL -- consultant/viewer currently sees all projects on scope=all

- [ ] **Step 3: Modify project_list to filter by role**

In `projects/views.py`, replace line 84:

```python
    projects = Project.objects.filter(organization=org)
```

With role-based filtering:

```python
    # Role-based filtering: consultant/viewer see only assigned projects
    membership = request.user.membership
    if membership.role == "owner":
        projects = Project.objects.filter(organization=org)
    else:
        projects = Project.objects.filter(
            organization=org, assigned_consultants=request.user
        )
```

All subsequent code (scope filter, client filter, status filter, sorting, grouping, pagination) continues to use the `projects` variable unchanged.

**Note on scope filter interaction:** The existing `scope=mine` filter (lines 87-91) further narrows by `assigned_consultants | created_by`. For non-owners, since the base queryset already limits to `assigned_consultants`, the `scope=mine` filter becomes redundant but harmless. For owners, `scope=mine` still provides the expected "my projects" view. When `scope=all`, non-owners still see only assigned projects (enforced by base queryset), while owners see all org projects.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: All tests PASS

Run: `uv run pytest -v`
Expected: All existing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): filter project list by consultant assignment"
```

---

## Tempering Rulings Applied

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| I-R1-01 | CRITICAL | Failing test won't fail (scope=mine already filters) | ACCEPTED -- Tests use scope=all, added created_by-only case |
| I-R1-02 | CRITICAL | Variable name mismatch (qs vs projects) | ACCEPTED -- Use projects variable consistently |
| I-R1-03 | CRITICAL | --timeout=30 not available | ACCEPTED -- Changed to uv run pytest -v |
| I-R1-04 | MAJOR | Owner test insufficient (only own project) | ACCEPTED -- Added other user's project, test scope=all |
| I-R1-05 | MAJOR | Missing viewer role test | ACCEPTED -- Parametrized test for consultant and viewer |
| I-R1-06 | MINOR | Missing imports in test snippet | REBUTTED -- Existing file has base imports |

<!-- forge:t06:구현담금질:complete:2026-04-12T17:45:00+09:00 -->
