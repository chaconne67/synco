# Phase 2 구현 계획: 뷰 보호 + 프로젝트 필터링 + 사이드바

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1에서 만든 데코레이터를 기존 뷰에 적용하고, _get_org를 active 필터로 수정하고, 프로젝트 목록을 consultant 역할에 맞게 필터링하고, 사이드바 메뉴를 역할별로 분기한다.

**Prerequisites:** Phase 1 완료 (InviteCode, Membership.status, decorators, context_processors, onboarding flow)

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, pytest

**Design spec:** `docs/plans/headhunting-onboarding/phase2/design.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | _get_org 수정, dashboard 보호, project_list 필터링, 권한 데코레이터 적용 |
| `clients/views.py` | 수정 | _get_org 수정, 권한 데코레이터 적용 |
| `templates/common/nav_sidebar.html` | 수정 | 역할별 메뉴 필터링 |
| `templates/common/nav_bottom.html` | 수정 | 역할별 메뉴 필터링 (모바일) |
| `tests/conftest.py` | 수정 | Membership.status='active' 추가 |
| `tests/accounts/test_rbac.py` | 수정 | 뷰 권한 통합 테스트 추가 |

---

### Task 4: _get_org 수정 + dashboard 보호

**Files:**
- Modify: `projects/views.py:59-61`
- Modify: `projects/views.py:2358-2398` (dashboard)
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update test fixtures to include Membership.status**

In `tests/conftest.py`, update the `user` fixture (line 19):

```python
@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org, status="active")
    return u
```

Update `other_user` fixture (line 26):

```python
@pytest.fixture
def other_user(db, org):
    u = User.objects.create_user(username="consultant2", password="testpass123")
    Membership.objects.create(user=u, organization=org, status="active")
    return u
```

Update `other_org_user` fixture (line 34):

```python
@pytest.fixture
def other_org_user(db):
    other_org = Organization.objects.create(name="Other Org")
    u = User.objects.create_user(username="outsider", password="testpass123")
    Membership.objects.create(user=u, organization=other_org, status="active")
    return u
```

- [ ] **Step 2: Modify _get_org to filter by active status**

In `projects/views.py`, replace lines 59-61:

```python
def _get_org(request):
    """Return the current user's Organization via active Membership, or 404."""
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status="active",
    )
```

- [ ] **Step 3: Add membership_required to dashboard view**

In `projects/views.py`, add import at top:

```python
from accounts.decorators import membership_required
```

Update the dashboard function (line 2358):

```python
@login_required
@membership_required
def dashboard(request):
```

- [ ] **Step 4: Run existing tests to verify nothing breaks**

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py tests/conftest.py
git commit -m "feat(projects): update _get_org to require active membership"
```

---

### Task 5: 기존 view에 권한 데코레이터 적용

**Files:**
- Modify: `projects/views.py` — owner-only views에 `@role_required("owner")` 추가
- Modify: `clients/views.py` — create/update/delete에 `@role_required("owner")` 추가
- Modify: `clients/views.py` — _get_org 수정
- Test: `tests/accounts/test_rbac.py` (기존 파일에 추가)

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
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 403

    def test_owner_can_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 200

    def test_consultant_cannot_create_project(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con2", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/projects/new/")
        assert response.status_code == 403

    def test_consultant_can_read_client_list(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con3", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/clients/")
        assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestViewPermissions -v`
Expected: FAIL — consultant can currently access all views (200 instead of 403)

- [ ] **Step 3: Apply role_required to clients/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Add `@membership_required` to all views. Add `@role_required("owner")` to write views:

```python
# client_list — all roles can read
@login_required
@membership_required
def client_list(request):
    ...

# client_create — owner only
@login_required
@role_required("owner")
def client_create(request):
    ...

# client_detail — all roles can read
@login_required
@membership_required
def client_detail(request, pk):
    ...

# client_update — owner only
@login_required
@role_required("owner")
def client_update(request, pk):
    ...

# client_delete — owner only
@login_required
@role_required("owner")
def client_delete(request, pk):
    ...

# contract_create — owner only
@login_required
@role_required("owner")
def contract_create(request, pk):
    ...

# contract_update — owner only
@login_required
@role_required("owner")
def contract_update(request, pk, contract_pk):
    ...

# contract_delete — owner only
@login_required
@role_required("owner")
def contract_delete(request, pk, contract_pk):
    ...
```

Apply `@role_required("owner")` to all reference views in `clients/views.py` (university/company/cert CRUD, import, export, autofill) — these are accessed via `/reference/` URLs defined in `clients/urls_reference.py`.

Also update `_get_org` in `clients/views.py` to filter by active status:

```python
def _get_org(request):
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status="active",
    )
```

- [ ] **Step 4: Apply role_required to projects/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Apply to owner-only views:

```python
# project_create — owner only
@login_required
@role_required("owner")
def project_create(request):
    ...

# project_delete — owner only
@login_required
@role_required("owner")
def project_delete(request, pk):
    ...

# approval_queue — owner only
@login_required
@role_required("owner")
def approval_queue(request):
    ...

# approval_decide — owner only
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

---

### Task 6: 프로젝트 목록 consultant 필터링

**Files:**
- Modify: `projects/views.py:78-170` (project_list)

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
        p1.consultants.add(consultant)

        # Project NOT assigned to consultant
        Project.objects.create(
            title="Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = __import__("django.test", fromlist=["Client"]).Client()
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

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(owner)

        response = test_client.get("/projects/")
        content = response.content.decode()
        assert "Project1" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: FAIL — consultant currently sees all projects

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
            organization=org, consultants=request.user
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

---

### Task 7: 사이드바 역할별 메뉴 필터링

**Files:**
- Modify: `templates/common/nav_sidebar.html`
- Modify: `templates/common/nav_bottom.html`

- [ ] **Step 1: Modify nav_sidebar.html**

Replace the entire content of `templates/common/nav_sidebar.html`:

```html
<div class="mb-8">
  <h1 class="text-heading font-bold text-primary">synco</h1>
</div>
<nav class="space-y-1 flex-1" id="sidebar-nav" aria-label="사이드바 네비게이션">
  <a href="/"
     hx-get="/" hx-target="#main-content" hx-push-url="true"
     data-nav="dashboard"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
    대시보드
  </a>
  <a href="/candidates/"
     hx-get="/candidates/" hx-target="#main-content" hx-push-url="true"
     data-nav="candidates"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
    후보자
  </a>
  <a href="/projects/"
     hx-get="/projects/" hx-target="#main-content" hx-push-url="true"
     data-nav="projects"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
    프로젝트
  </a>
  <a href="/clients/"
     hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
     data-nav="clients"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
    고객사
  </a>
  {% if membership and membership.role == 'owner' %}
  <a href="/reference/"
     hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
     data-nav="reference"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
    레퍼런스
  </a>
  {% endif %}
  {% if membership and membership.role == 'owner' and pending_approval_count and pending_approval_count > 0 %}
  <a href="/projects/approvals/"
     hx-get="/projects/approvals/" hx-target="#main-content" hx-push-url="true"
     data-nav="approvals"
     class="sidebar-tab flex items-center justify-between px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <span class="flex items-center gap-3">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
      승인 요청
    </span>
    <span class="bg-red-500 text-white text-[12px] font-bold rounded-full px-2 py-0.5">{{ pending_approval_count }}</span>
  </a>
  {% endif %}
  <a href="/news/"
     hx-get="/news/" hx-target="#main-content" hx-push-url="true"
     data-nav="news"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"/></svg>
    뉴스피드
    {% if has_new_news %}<span class="w-2 h-2 bg-red-500 rounded-full"></span>{% endif %}
  </a>
  {% if membership and membership.role == 'owner' %}
  <a href="/organization/"
     hx-get="/organization/" hx-target="#main-content" hx-push-url="true"
     data-nav="organization"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
    조직 관리
  </a>
  {% endif %}
  <a href="/accounts/settings/"
     hx-get="/accounts/settings/" hx-target="#main-content" hx-push-url="true"
     data-nav="settings"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
    설정
  </a>

<script>
function updateSidebar() {
  var path = window.location.pathname;
  document.querySelectorAll('.sidebar-tab').forEach(function(tab) {
    var key = tab.dataset.nav;
    var active = (key === 'dashboard' && (path === '/' || path.startsWith('/dashboard'))) ||
                 (key === 'candidates' && path.startsWith('/candidates')) ||
                 (key === 'projects' && path.startsWith('/projects')) ||
                 (key === 'clients' && path.startsWith('/clients')) ||
                 (key === 'reference' && path.startsWith('/reference')) ||
                 (key === 'approvals' && path.startsWith('/projects/approvals')) ||
                 (key === 'news' && path.startsWith('/news')) ||
                 (key === 'organization' && path.startsWith('/organization')) ||
                 (key === 'settings' && path.includes('/settings'));
    tab.className = 'sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] ' +
      (active ? 'bg-primary-light text-primary font-semibold' : 'text-gray-500 hover:bg-gray-50');
  });
}
updateSidebar();
document.body.addEventListener('htmx:pushedIntoHistory', updateSidebar);
document.body.addEventListener('htmx:replacedInHistory', updateSidebar);
</script>
</nav>
```

- [ ] **Step 2: Update nav_bottom.html similarly**

Apply the same `{% if membership and membership.role == 'owner' %}` guards to the mobile bottom navigation for reference and organization links.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html
git commit -m "feat(ui): filter sidebar and bottom nav menus by user role"
```
