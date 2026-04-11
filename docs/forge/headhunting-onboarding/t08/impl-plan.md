# Task 8: 프로젝트 생성 시 담당 컨설턴트 지정

**Goal:** 프로젝트 생성/수정 폼에 담당 컨설턴트 선택 필드를 추가하고, 미선택 시 생성자를 기본 담당자로 지정한다.

**Design spec:** `docs/forge/headhunting-onboarding/t08/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 5, Task 6

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/forms.py` | 수정 | ProjectForm에 assigned_consultants 필드 추가 |
| `projects/views.py` | 수정 | project_create, project_update에서 org 전달 및 기본 담당자 로직 |
| `tests/accounts/test_rbac.py` | 수정 | 컨설턴트 지정 테스트 추가 |

---

- [ ] **Step 1: Write failing test**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestProjectConsultantAssignment:
    def test_owner_can_assign_consultants_on_create(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_a", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con = User.objects.create_user(username="con_a", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co", organization=org)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "New Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "assigned_consultants": [str(con.pk)],
        }, follow=True)
        project = Project.objects.get(title="New Project")
        assert con in project.assigned_consultants.all()

    def test_no_consultants_defaults_to_owner(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_b", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Co2", organization=org)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Solo Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        project = Project.objects.get(title="Solo Project")
        assert owner in project.assigned_consultants.all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: FAIL

- [ ] **Step 3: Add assigned_consultants field to ProjectForm**

In `projects/forms.py`, add to `ProjectForm` the `assigned_consultants` field, and add initialization to filter by organization:

```python
assigned_consultants = forms.ModelMultipleChoiceField(
    queryset=User.objects.none(),
    required=False,
    widget=forms.CheckboxSelectMultiple,
    label="담당 컨설턴트",
)

def __init__(self, *args, org=None, **kwargs):
    super().__init__(*args, **kwargs)
    if org:
        self.fields["assigned_consultants"].queryset = User.objects.filter(
            membership__organization=org,
            membership__status="active",
        )
```

- [ ] **Step 4: Update project_create view**

In `projects/views.py`, within `project_create`, pass org to form and handle default consultant:

```python
form = ProjectForm(request.POST or None, request.FILES or None, org=org)
if form.is_valid():
    project = form.save(commit=False)
    project.organization = org
    project.created_by = request.user
    project.save()
    form.save_m2m()
    # Default: if no consultants selected, assign creator
    if not project.assigned_consultants.exists():
        project.assigned_consultants.add(request.user)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/forms.py projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): add consultant assignment on project create/update"
```
