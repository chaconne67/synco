# Phase 3 구현 계획: 컨설턴트 지정 + 빈 화면 CTA + 통합 검증

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로젝트 생성/수정 시 담당 컨설턴트 지정 기능을 추가하고, 역할별 빈 화면 CTA를 구현하고, 전체 RBAC+온보딩 기능을 통합 검증한다.

**Prerequisites:** Phase 1 (모델+데코레이터+온보딩), Phase 2 (뷰 보호+필터링+사이드바) 완료

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, pytest

**Design spec:** `docs/plans/headhunting-onboarding/phase3/design.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/forms.py` | 수정 | ProjectForm에 consultants 필드 추가 |
| `projects/views.py` | 수정 | project_create/update에 org 전달, 기본 담당자 로직 |
| `projects/templates/projects/partials/view_board.html` | 수정 | 프로젝트 빈 화면 CTA |
| `clients/templates/clients/client_list.html` | 수정 | 고객사 빈 화면 CTA |
| `tests/accounts/test_rbac.py` | 수정 | 컨설턴트 지정 테스트 추가 |

---

### Task 8: 프로젝트 생성 시 담당 컨설턴트 지정

**Files:**
- Modify: `projects/forms.py` (ProjectForm)
- Modify: `projects/views.py` (project_create, project_update)

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

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "New Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "consultants": [str(con.pk)],
        }, follow=True)
        project = Project.objects.get(title="New Project")
        assert con in project.consultants.all()

    def test_no_consultants_defaults_to_owner(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_b", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Co2", organization=org)

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Solo Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        project = Project.objects.get(title="Solo Project")
        assert owner in project.consultants.all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: FAIL

- [ ] **Step 3: Add consultants field to ProjectForm**

In `projects/forms.py`, add to `ProjectForm.Meta.fields` the `consultants` field, and add initialization to filter by organization:

```python
consultants = forms.ModelMultipleChoiceField(
    queryset=User.objects.none(),
    required=False,
    widget=forms.CheckboxSelectMultiple,
    label="담당 컨설턴트",
)

def __init__(self, *args, org=None, **kwargs):
    super().__init__(*args, **kwargs)
    if org:
        self.fields["consultants"].queryset = User.objects.filter(
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
    if not project.consultants.exists():
        project.consultants.add(request.user)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/forms.py projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): add consultant assignment on project create/update"
```

---

### Task 9: 빈 화면 CTA (역할별 분기)

**Files:**
- Modify: `projects/templates/projects/partials/view_board.html` (or equivalent empty state)
- Modify: `clients/templates/clients/client_list.html`

- [ ] **Step 1: Update project list empty state**

In the project list template, find the empty state section and add role-based CTA:

```html
{% if not projects %}
<div class="flex flex-col items-center justify-center py-16 text-center">
  <svg class="w-12 h-12 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
  </svg>
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">프로젝트가 없습니다.</p>
    <a href="{% url 'projects:project_create' %}"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      새 프로젝트 만들기
    </a>
  {% else %}
    <p class="text-gray-500">배정된 프로젝트가 없습니다.</p>
    <p class="text-gray-400 text-sm mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 2: Update client list empty state**

```html
{% if not clients %}
<div class="flex flex-col items-center justify-center py-16 text-center">
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">등록된 고객사가 없습니다.</p>
    <a href="{% url 'clients:client_create' %}"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      첫 고객사를 등록하세요
    </a>
  {% else %}
    <p class="text-gray-500">등록된 고객사가 없습니다.</p>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 3: Update dashboard empty state**

In the dashboard template, add owner-specific CTA when no data:

```html
{% if not today_actions and not weekly_schedule %}
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">아직 진행 중인 업무가 없습니다.</p>
    <a href="/clients/"
       hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      고객사를 등록하고 첫 프로젝트를 시작하세요
    </a>
  {% else %}
    <p class="text-gray-500">배정된 프로젝트가 없습니다.</p>
    <p class="text-gray-400 text-sm mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
{% endif %}
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/templates/ clients/templates/
git commit -m "feat(ui): add role-based empty state CTAs for projects, clients, dashboard"
```

---

### Task 10: 전체 통합 검증

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors

- [ ] **Step 3: Check migrations**

Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 4: Manual verification checklist**

Start dev server: `./dev.sh`

1. 카카오 로그인 → Membership 없음 → 초대코드 입력 화면 표시
2. 유효한 owner 코드 입력 → 즉시 대시보드
3. 유효한 consultant 코드 입력 → 승인 대기 화면
4. Django admin에서 Membership.status=active 변경 → 대시보드 접근 가능
5. consultant로 로그인 → 사이드바에 레퍼런스/조직관리 메뉴 없음
6. consultant로 /clients/new/ 직접 접근 → 403
7. consultant로 프로젝트 목록 → 배정된 것만 표시
8. owner로 프로젝트 생성 → 담당 컨설턴트 선택 가능

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete RBAC + onboarding (Plan 1/3)"
```
