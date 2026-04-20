# Dashboard Phase 2a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire real data into dashboard cards S1-1 Monthly Success, S1-3 Project Status, S2-1 Team Performance, S3 Weekly Schedule, S3 Monthly Calendar without adding new models.

**Architecture:** Extend `projects/services/dashboard.py` with a single public function `get_dashboard_context(org, user, membership)` that returns a context dict. The view passes this dict to the existing `dash_full.html` template which replaces hardcoded values with Django template expressions. All queries derive from existing `Project`, `Application`, `ActionItem`, `Interview`, `Membership` models.

**Tech Stack:** Django 5.2 ORM · pytest-django · HTMX · Tailwind (design tokens in `static/css/input.css`).

**Spec:** `docs/superpowers/specs/2026-04-20-dashboard-phase2a-design.md`

---

## File Structure

**Service:**
- Modify `projects/services/dashboard.py` — add `get_dashboard_context()` + private helpers

**View:**
- Modify `projects/views.py:2141-2147` — call `get_dashboard_context()` and pass as context

**Template:**
- Modify `projects/templates/projects/partials/dash_full.html` — replace hardcoded values with `{{ }}` / `{% for %}`

**Tests:**
- Create `tests/test_dashboard_phase2a.py` — view-level pytest-django tests

---

## Key Codebase Facts (engineers start here)

- **`@membership_required`** does NOT attach attributes to `request`. Retrieve org/membership via `request.user.membership` (`User` → `Membership` is OneToOne) and `request.user.membership.organization`.
- **`Membership.Role`** enum values: `"owner"`, `"consultant"`, `"viewer"`.
- **`Project`** fields: `status` (`"open"`/`"closed"`), `phase` (`"searching"`/`"screening"`), `result` (`"success"`/`"fail"`/`""`), `closed_at`, `organization` FK, `assigned_consultants` M2M (related_name `"assigned_projects"`).
- **`ActionItem`** fields: `application` FK → Application → `project` FK → Project. `action_type` FK → `ActionType` (use `.code` string). `scheduled_at` DateTimeField (nullable), `title`, `assigned_to` FK → User.
- **`Interview`** fields: `action_item` OneToOne → ActionItem (use `action_item.application.project` chain). `scheduled_at` DateTimeField (not-null). `type`, `location`, `round`.
- **`User`** inherits `AbstractUser`: `first_name`, `last_name`, `username`, `get_full_name()`. Korean name convention in this codebase: samples usually have Korean name stored in `last_name` only (e.g. `last_name="김민호"`) or split — check actual data in Task 4. Fallback chain: `last_name + first_name` (trimmed) → `get_full_name()` → `username`.
- **Existing service** `projects/services/dashboard.py` already has `get_today_actions()` and `get_project_kanban_cards()`. Add new helpers alongside.
- **Existing test pattern:** `tests/test_clients_views_list.py` uses `pytest.fixture` for `org`, `owner`, `owner_client` (Django `client.force_login`). Follow this.

---

## Task 1: Skeleton — `get_dashboard_context` + view wiring

**Files:**
- Modify: `projects/services/dashboard.py`
- Modify: `projects/views.py:2141-2147`
- Create: `tests/test_dashboard_phase2a.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_dashboard_phase2a.py` with this content:

```python
import pytest
from django.urls import reverse

from accounts.models import Membership, Organization, User


@pytest.fixture
def org(db):
    return Organization.objects.create(name="TestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_dashboard_renders_with_empty_org(owner_client):
    """Skeleton: dashboard renders 200 with empty org, no crash."""
    resp = owner_client.get(reverse("dashboard"))
    assert resp.status_code == 200
    # Template still contains hardcoded structure
    assert b"Monthly Success" in resp.content
```

- [ ] **Step 2: Run test — expect PASS (hardcoded template still works)**

Run: `uv run pytest tests/test_dashboard_phase2a.py::test_dashboard_renders_with_empty_org -v`
Expected: PASS (existing view works)

- [ ] **Step 3: Add skeleton function to `projects/services/dashboard.py`**

Append to `projects/services/dashboard.py`:

```python
def get_dashboard_context(org: Organization, user: User, membership) -> dict:
    """대시보드 카드 전체 컨텍스트.

    Phase 2a: S1-1 Monthly Success, S1-3 Project Status,
              S2-1 Team Performance, S3 Weekly/Monthly Calendar.
    Phase 2b 카드(S1-2 Revenue, S2-2 Recent Activity)는 하드코딩 유지.
    """
    scope_owner = membership.role == "owner"
    return {
        "monthly_success": None,
        "project_status": None,
        "team_performance": None,
        "weekly_schedule": None,
        "monthly_calendar": None,
        "_scope_owner": scope_owner,
    }


def _scope_projects(org: Organization, user: User, scope_owner: bool):
    """권한 스코프 공통 쿼리셋. owner=조직 전체, 아니면 본인 담당만."""
    qs = Project.objects.filter(organization=org)
    if not scope_owner:
        qs = qs.filter(assigned_consultants=user)
    return qs
```

- [ ] **Step 4: Wire view in `projects/views.py:2141-2147`**

Replace:
```python
@login_required
@membership_required
def dashboard(request):
    """대시보드 메인 화면 (Phase 1: 하드코딩 목업)."""
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html")
    return render(request, "projects/dashboard.html")
```

With:
```python
@login_required
@membership_required
def dashboard(request):
    """대시보드 메인 화면 (Phase 2a: 실데이터 연결 진행 중)."""
    membership = request.user.membership
    ctx = get_dashboard_context(membership.organization, request.user, membership)
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", ctx)
    return render(request, "projects/dashboard.html", ctx)
```

Add import at top of `projects/views.py` (check existing imports; likely needs to be added if not there):
```python
from projects.services.dashboard import get_dashboard_context
```

- [ ] **Step 5: Run test — expect still PASS**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite to catch regressions**

Run: `uv run pytest -x -q`
Expected: All green (or only unrelated pre-existing failures).

- [ ] **Step 7: Commit**

```bash
git add projects/services/dashboard.py projects/views.py tests/test_dashboard_phase2a.py
git commit -m "feat(dashboard): scaffold get_dashboard_context + scope helper

- 공개 API get_dashboard_context(org, user, membership) 추가 (빈 dict)
- _scope_projects 권한 스코프 헬퍼 추가 (owner=전체, 그 외=본인 담당)
- dashboard() 뷰가 컨텍스트를 템플릿에 전달
- 기존 하드코딩 템플릿은 유지 (변수 참조 없음)"
```

---

## Task 2: S1-1 Monthly Success

**Files:**
- Modify: `projects/services/dashboard.py`
- Modify: `projects/templates/projects/partials/dash_full.html:9-28`
- Modify: `tests/test_dashboard_phase2a.py`

**Semantics recap (from spec):**
- 큰 숫자 = 이번 달 성공 건수 (`status=CLOSED AND result="success" AND closed_at >= 이번달 1일`)
- 진행 중 = `status=OPEN` 건수 (누적)
- 성공률 = `이번 달 성공 / (이번 달 성공 + 이번 달 실패)`, 분모 0 → None (템플릿에서 "—")

- [ ] **Step 1: Write failing test**

Append to `tests/test_dashboard_phase2a.py`:

```python
from datetime import timedelta

from django.utils import timezone

from clients.models import Client
from projects.models import Project


def _close_project(project, result, at):
    """Helper: close a project at specific datetime."""
    Project.objects.filter(pk=project.pk).update(
        status="closed", result=result, closed_at=at
    )


@pytest.fixture
def client_obj(org):
    return Client.objects.create(organization=org, name="ClientCo")


@pytest.mark.django_db
def test_s1_monthly_success_counts(owner_client, org, client_obj):
    """S1-1: 이번 달 성공/진행중/성공률 렌더."""
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = month_start - timedelta(days=1)

    # 이번 달 성공 2건
    for i in range(2):
        p = Project.objects.create(organization=org, client=client_obj, title=f"S{i}")
        _close_project(p, "success", month_start + timedelta(days=1))
    # 이번 달 실패 1건
    p = Project.objects.create(organization=org, client=client_obj, title="F1")
    _close_project(p, "fail", month_start + timedelta(days=2))
    # 지난 달 성공 (제외되어야 함)
    p = Project.objects.create(organization=org, client=client_obj, title="OLD")
    _close_project(p, "success", last_month)
    # 진행 중 3건
    for i in range(3):
        Project.objects.create(organization=org, client=client_obj, title=f"O{i}")

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # 큰 숫자 = 이번 달 성공 2건
    assert 'data-testid="s1-success-count">2<' in body
    # 진행 중 = 3건
    assert 'data-testid="s1-active-count">3<' in body
    # 성공률 = 2 / (2+1) = 67%
    assert 'data-testid="s1-success-rate">67<' in body


@pytest.mark.django_db
def test_s1_monthly_success_empty(owner_client):
    """S1-1 빈 조직: 0/0/— 렌더."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert 'data-testid="s1-success-count">0<' in body
    assert 'data-testid="s1-active-count">0<' in body
    assert 'data-testid="s1-success-rate">—<' in body
```

- [ ] **Step 2: Run test — expect FAIL (no data-testid yet)**

Run: `uv run pytest tests/test_dashboard_phase2a.py::test_s1_monthly_success_counts tests/test_dashboard_phase2a.py::test_s1_monthly_success_empty -v`
Expected: FAIL — `data-testid="s1-success-count"` not in body.

- [ ] **Step 3: Implement `_monthly_success` helper**

In `projects/services/dashboard.py`, add helper and wire into `get_dashboard_context`:

```python
def _monthly_success(org, user, scope_owner):
    """S1-1 Monthly Success: 이번 달 성공·진행중·성공률."""
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = _scope_projects(org, user, scope_owner)

    closed_this_month = qs.filter(
        status=ProjectStatus.CLOSED,
        closed_at__gte=month_start,
    )
    success = closed_this_month.filter(result=ProjectResult.SUCCESS).count()
    fail = closed_this_month.filter(result=ProjectResult.FAIL).count()
    active = qs.filter(status=ProjectStatus.OPEN).count()
    total = success + fail
    return {
        "success_count": success,
        "active_count": active,
        "success_rate": round(success / total * 100) if total else None,
    }
```

Update imports in `projects/services/dashboard.py`:
```python
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Project,
    ProjectPhase,
    ProjectResult,
    ProjectStatus,
)
```

Update `get_dashboard_context` body:
```python
    return {
        "monthly_success": _monthly_success(org, user, scope_owner),
        "project_status": None,
        "team_performance": None,
        "weekly_schedule": None,
        "monthly_calendar": None,
        "_scope_owner": scope_owner,
    }
```

- [ ] **Step 4: Update template S1-1 card (`dash_full.html:9-28`)**

Replace the `<article>` block for Monthly Success with:

```html
      <article class="col-span-4 bg-surface rounded-card shadow-card p-6 flex flex-col">
        <div class="flex items-start justify-between">
          <div class="eyebrow">Monthly Success</div>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
        </div>
        <div class="mt-6 flex items-baseline gap-3">
          <span class="text-4xl leading-none font-bold tnum" data-testid="s1-success-count">{{ monthly_success.success_count }}</span>
          <span class="text-sm text-muted">성공 프로젝트</span>
        </div>
        <div class="mt-6 pt-5 border-t border-line grid grid-cols-2 gap-4">
          <div>
            <div class="eyebrow eyebrow-ko">진행 중</div>
            <div class="mt-1 text-xl font-bold tnum" data-testid="s1-active-count">{{ monthly_success.active_count }}</div>
          </div>
          <div>
            <div class="eyebrow eyebrow-ko">성공률</div>
            <div class="mt-1 text-xl font-bold tnum"><span data-testid="s1-success-rate">{% if monthly_success.success_rate is None %}—{% else %}{{ monthly_success.success_rate }}{% endif %}</span>{% if monthly_success.success_rate is not None %}<span class="text-sm text-muted font-medium">%</span>{% endif %}</div>
          </div>
        </div>
      </article>
```

Note: label changed from "종료된 프로젝트" to "성공 프로젝트" to match confirmed semantic (success count only).

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/services/dashboard.py projects/templates/projects/partials/dash_full.html tests/test_dashboard_phase2a.py
git commit -m "feat(dashboard): S1-1 Monthly Success 실데이터

- _monthly_success(): 이번 달 success/active/rate 집계
- 라벨 '종료된 프로젝트' → '성공 프로젝트' (의미 일치)
- 분모 0 성공률 '—' 처리
- data-testid 로 테스트"
```

---

## Task 3: S1-3 Project Status

**Files:**
- Modify: `projects/services/dashboard.py`
- Modify: `projects/templates/projects/partials/dash_full.html:49-77`
- Modify: `tests/test_dashboard_phase2a.py`

**Semantics:**
- 진행(success dot) = `status=OPEN AND phase=SEARCHING` 개수
- 심사(warning dot) = `status=OPEN AND phase=SCREENING` 개수
- 완료(info dot) = `status=CLOSED` 개수 (성공+실패 합산)

- [ ] **Step 1: Write failing test**

Append to `tests/test_dashboard_phase2a.py`:

```python
@pytest.mark.django_db
def test_s1_project_status_counts(owner_client, org, client_obj):
    """S1-3: 서칭/스크리닝/완료 개수 렌더."""
    # 서칭 4건
    for i in range(4):
        Project.objects.create(
            organization=org, client=client_obj, title=f"SR{i}",
            status="open", phase="searching",
        )
    # 스크리닝 2건
    for i in range(2):
        Project.objects.create(
            organization=org, client=client_obj, title=f"SC{i}",
            status="open", phase="screening",
        )
    # 완료 3건 (성공 2 + 실패 1)
    for i, res in enumerate(["success", "success", "fail"]):
        p = Project.objects.create(
            organization=org, client=client_obj, title=f"CL{i}",
        )
        _close_project(p, res, timezone.now())

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    assert 'data-testid="s3-searching">4<' in body
    assert 'data-testid="s3-screening">2<' in body
    assert 'data-testid="s3-closed">3<' in body
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_dashboard_phase2a.py::test_s1_project_status_counts -v`
Expected: FAIL — `data-testid="s3-searching"` not in body.

- [ ] **Step 3: Implement `_project_status_counts` helper**

Add to `projects/services/dashboard.py`:

```python
def _project_status_counts(org, user, scope_owner):
    """S1-3 Project Status: searching/screening/closed 누적 개수."""
    qs = _scope_projects(org, user, scope_owner)
    return {
        "searching": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SEARCHING
        ).count(),
        "screening": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SCREENING
        ).count(),
        "closed": qs.filter(status=ProjectStatus.CLOSED).count(),
    }
```

Update `get_dashboard_context`:
```python
        "project_status": _project_status_counts(org, user, scope_owner),
```

- [ ] **Step 4: Update template S1-3 card (`dash_full.html:49-77`)**

Replace the `<article>` block for Project Status with:

```html
      <article class="col-span-4 bg-surface rounded-card shadow-card p-6">
        <div class="flex items-start justify-between">
          <div class="eyebrow">Project Status</div>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect width="4" height="7" x="7" y="10" rx="1"/><rect width="4" height="12" x="15" y="5" rx="1"/></svg>
        </div>
        <ul class="mt-6 space-y-4">
          <li class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot bg-success"></span>
              <span class="text-sm font-medium text-ink2">진행</span>
            </div>
            <span class="text-lg font-bold tnum" data-testid="s3-searching">{{ project_status.searching }}</span>
          </li>
          <li class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot bg-warning"></span>
              <span class="text-sm font-medium text-ink2">심사</span>
            </div>
            <span class="text-lg font-bold tnum" data-testid="s3-screening">{{ project_status.screening }}</span>
          </li>
          <li class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot bg-info"></span>
              <span class="text-sm font-medium text-ink2">완료</span>
            </div>
            <span class="text-lg font-bold tnum" data-testid="s3-closed">{{ project_status.closed }}</span>
          </li>
        </ul>
      </article>
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/services/dashboard.py projects/templates/projects/partials/dash_full.html tests/test_dashboard_phase2a.py
git commit -m "feat(dashboard): S1-3 Project Status 실데이터

- _project_status_counts(): searching/screening/closed 개수"
```

---

## Task 4: S2-1 Team Performance

**Files:**
- Modify: `projects/services/dashboard.py`
- Modify: `projects/templates/projects/partials/dash_full.html:83-148`
- Modify: `tests/test_dashboard_phase2a.py`

**Semantics:**
- 조직의 Membership where `role in (owner, consultant)` 전체. Viewer 제외. 스코프 무관(owner/consultant 로그인 무관).
- 각 멤버 1줄: 아바타(회색 원), 이름(한글 display name), 역할(owner→대표, consultant→컨설턴트), 현재 진행 중 프로젝트 건수(`assigned_projects.filter(status=OPEN)`), 누적 성공률.
- 성공률 = `본인 담당 closed+success / 본인 담당 closed`. 분모 0 → `None`.
- progress bar 색: `≥80% success` / `≥60% default` / 그 이하 `info`. None 이면 0% + default.
- 정렬: `success_rate DESC NULLS LAST` (None 인 멤버는 맨 아래).

**Display name convention:**
Python helper `_display_name(user)`:
1. `user.last_name.strip()` + `user.first_name.strip()` 합쳐서 (공백 없이) 반환 if any part non-empty.
2. 아니면 `user.get_full_name().strip()`.
3. 아니면 `user.username`.

- [ ] **Step 1: Write failing test**

Append to `tests/test_dashboard_phase2a.py`:

```python
@pytest.fixture
def consultant_user(org):
    u = User.objects.create_user(
        username="c1", password="x", first_name="민호", last_name="김"
    )
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.mark.django_db
def test_s2_team_performance_lists_members(owner_client, org, client_obj, consultant_user):
    """S2-1: owner + consultant 목록, viewer 제외."""
    viewer = User.objects.create_user(username="v1", password="x", first_name="뷰어")
    Membership.objects.create(user=viewer, organization=org, role="viewer")

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # consultant 한글명 표시
    assert "김민호" in body
    # owner 본인도 표시 (username="owner" fallback)
    assert "owner" in body
    # viewer 제외
    assert "뷰어" not in body
    # 역할 한글
    assert "컨설턴트" in body
    assert "대표" in body


@pytest.mark.django_db
def test_s2_team_performance_success_rate(owner_client, org, client_obj, consultant_user):
    """S2-1: 성공률 = 본인 담당 success / 본인 담당 closed."""
    # consultant가 담당한 프로젝트 4건 closed (3성공 1실패) + 2 open
    for i in range(3):
        p = Project.objects.create(organization=org, client=client_obj, title=f"S{i}")
        p.assigned_consultants.add(consultant_user)
        _close_project(p, "success", timezone.now())
    p = Project.objects.create(organization=org, client=client_obj, title="F")
    p.assigned_consultants.add(consultant_user)
    _close_project(p, "fail", timezone.now())
    for i in range(2):
        p = Project.objects.create(
            organization=org, client=client_obj, title=f"O{i}", status="open"
        )
        p.assigned_consultants.add(consultant_user)

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # 성공률 75% (3/4)
    assert 'data-testid="s2-rate-c1">75<' in body
    # 현재 프로젝트 2건
    assert 'data-testid="s2-active-c1">2건 진행 중<' in body


@pytest.mark.django_db
def test_s2_team_performance_empty_rate(owner_client, org, consultant_user):
    """S2-1: 표본 없는 멤버는 '—', 정렬 맨 아래."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    assert 'data-testid="s2-rate-c1">—<' in body
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v -k s2_`
Expected: FAIL — names not in body, testids missing.

- [ ] **Step 3: Implement `_team_performance` + `_display_name` helpers**

Add to `projects/services/dashboard.py`:

```python
from accounts.models import Membership


_ROLE_LABEL_KO = {
    "owner": "대표",
    "consultant": "컨설턴트",
}


def _display_name(user) -> str:
    """한글 이름 표시. last+first → get_full_name → username."""
    parts = (user.last_name or "").strip() + (user.first_name or "").strip()
    if parts:
        return parts
    full = (user.get_full_name() or "").strip()
    if full:
        return full
    return user.username


def _progress_color(rate):
    """S2-1 progress bar 색상 클래스. rate=None → default."""
    if rate is None:
        return ""
    if rate >= 80:
        return "success"
    if rate >= 60:
        return ""
    return "info"


def _team_performance(org):
    """S2-1 Team Performance: owner+consultant 전체, 누적 성공률 desc.

    Viewer 제외. 표본 없는 멤버(rate=None)는 맨 아래.
    """
    memberships = (
        Membership.objects.filter(
            organization=org,
            role__in=["owner", "consultant"],
            status="active",
        )
        .select_related("user")
    )
    rows = []
    for m in memberships:
        user = m.user
        assigned = user.assigned_projects.filter(organization=org)
        active_count = assigned.filter(status=ProjectStatus.OPEN).count()
        closed = assigned.filter(status=ProjectStatus.CLOSED)
        closed_total = closed.count()
        success_count = closed.filter(result=ProjectResult.SUCCESS).count()
        rate = round(success_count / closed_total * 100) if closed_total else None

        rows.append({
            "username": user.username,
            "display_name": _display_name(user),
            "role_label": _ROLE_LABEL_KO.get(m.role, m.role),
            "active_count": active_count,
            "success_rate": rate,
            "progress_color": _progress_color(rate),
        })

    # sort: rate desc NULLS LAST
    rows.sort(key=lambda r: (r["success_rate"] is None, -(r["success_rate"] or 0)))
    return rows
```

Update `get_dashboard_context`:
```python
        "team_performance": _team_performance(org),
```

- [ ] **Step 4: Replace template S2-1 card (`dash_full.html:83-148`)**

Replace the Team Performance `<article>` with:

```html
      <article class="col-span-8 bg-surface rounded-card shadow-card p-6">
        <div class="flex items-center justify-between">
          <div class="eyebrow">Team Performance</div>
          <button type="button" aria-disabled="true" class="text-xs font-semibold text-ink3 hover:underline">전체 멤버 보기 →</button>
        </div>

        <ul class="mt-6 space-y-5">
          {% for m in team_performance %}
          <li class="flex items-center gap-4">
            <div aria-hidden="true" class="w-11 h-11 rounded-full bg-line"></div>
            <div class="w-[180px] shrink-0">
              <div class="text-sm font-semibold">{{ m.display_name }}</div>
              <div class="eyebrow eyebrow-ko mt-0.5 !text-faint">{{ m.role_label }}</div>
            </div>
            <div class="w-[140px] shrink-0">
              <div class="eyebrow eyebrow-ko">현재 프로젝트</div>
              <div class="text-sm font-semibold mt-0.5" data-testid="s2-active-{{ m.username }}">{{ m.active_count }}건 진행 중</div>
            </div>
            <div class="flex-1">
              <div class="flex items-center justify-between mb-1.5">
                <div class="eyebrow eyebrow-ko">성공률</div>
                <div class="text-xs font-semibold tnum text-ink3"><span data-testid="s2-rate-{{ m.username }}">{% if m.success_rate is None %}—{% else %}{{ m.success_rate }}%{% endif %}</span></div>
              </div>
              <div class="progress {{ m.progress_color }}"><span style="width:{% if m.success_rate %}{{ m.success_rate }}{% else %}0{% endif %}%"></span></div>
            </div>
          </li>
          {% endfor %}
        </ul>
      </article>
```

Note: 아바타 `<div>` 에서 gradient 클래스 제거, 이니셜 텍스트 제거 (스켈레톤 `bg-line` 회색 원만). Phase 1 eyebrow 제목 "달성률" → "성공률" 변경.

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/services/dashboard.py projects/templates/projects/partials/dash_full.html tests/test_dashboard_phase2a.py
git commit -m "feat(dashboard): S2-1 Team Performance 실데이터

- _team_performance(): owner+consultant 전체, 누적 성공률 desc
- Viewer 제외, 표본 없는 멤버는 맨 아래
- 아바타 스켈레톤 처리 (추후 photo 필드로 교체)
- eyebrow '달성률' → '성공률'"
```

---

## Task 5: S3 Weekly Schedule

**Files:**
- Modify: `projects/services/dashboard.py`
- Modify: `projects/templates/projects/partials/dash_full.html:203-239`
- Modify: `tests/test_dashboard_phase2a.py`

**Semantics:**
- 범위: 이번 주 월요일 00:00 ~ 다음 주 월요일 00:00 (now 기준).
- 소스 합집합: `Interview.scheduled_at`, `ActionItem.scheduled_at` (due_at 미사용).
- 정렬: scheduled_at asc, 최대 5개.
- 스코프: owner=org 전체. consultant/viewer=본인 담당 프로젝트의 이벤트 + 본인 assignee인 ActionItem.
- 각 이벤트 표시 필드:
  - `scheduled_at`
  - `label_color`: Interview → `info` / ActionItem.action_type.code in {"submit_to_client", "pre_meeting"} → `warning` / else → `ink3`
  - `title`: Interview 는 `"{n}차 면접"` / ActionItem 은 `item.title`
  - `subtitle`: Interview 는 `"후보자: {candidate.name} · {location or '-'}"` / ActionItem 은 `"{project.title} · {client.name}"`
- 빈 상태: `[]` 반환, 템플릿에서 "이번 주 일정이 없습니다" 카드 1개 렌더.

- [ ] **Step 1: Write failing test**

Append to `tests/test_dashboard_phase2a.py`:

```python
from candidates.models import Candidate
from projects.models import (
    ActionItem,
    ActionType,
    Application,
    Interview,
)


def _this_monday_midnight():
    now = timezone.now()
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture
def interview_type(db):
    return ActionType.objects.create(code="interview_round", label_ko="면접")


@pytest.fixture
def submit_type(db):
    return ActionType.objects.create(code="submit_to_client", label_ko="서류 제출")


@pytest.mark.django_db
def test_s3_weekly_empty(owner_client):
    """S3 Weekly: 빈 상태 렌더."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert "이번 주 일정이 없습니다" in body


@pytest.mark.django_db
def test_s3_weekly_shows_interview(
    owner_client, org, client_obj, interview_type, consultant_user
):
    """S3 Weekly: Interview 표시, '인터뷰' 키워드·후보자명 포함."""
    monday = _this_monday_midnight()
    cand = Candidate.objects.create(organization=org, name="박해준")
    proj = Project.objects.create(organization=org, client=client_obj, title="P1")
    app = Application.objects.create(project=proj, candidate=cand)
    ai = ActionItem.objects.create(
        application=app,
        action_type=interview_type,
        title="1차 면접",
        scheduled_at=monday + timedelta(days=2, hours=11),
    )
    Interview.objects.create(
        action_item=ai, round=1, scheduled_at=monday + timedelta(days=2, hours=11),
        type="화상", location="Zoom",
    )

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert "1차 면접" in body
    assert "박해준" in body
    assert "이번 주 일정이 없습니다" not in body
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v -k s3_weekly`
Expected: FAIL — "이번 주 일정이 없습니다" not in body (hardcoded cards still present) and new rows not rendered.

- [ ] **Step 3: Implement `_weekly_schedule` helper**

Add to `projects/services/dashboard.py`:

```python
from datetime import timedelta

from projects.models import (
    ActionItem,
    ActionItemStatus,
    Interview,
    Project,
    ProjectPhase,
    ProjectResult,
    ProjectStatus,
)


_CLIENT_FACING_CODES = {"submit_to_client", "pre_meeting"}


def _week_range():
    now = timezone.now()
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    next_monday = monday + timedelta(days=7)
    return monday, next_monday


def _weekly_schedule(org, user, scope_owner, limit: int = 5):
    """S3 Weekly Schedule: 이번 주 Interview + ActionItem 합집합, 시간 asc."""
    monday, next_monday = _week_range()

    interviews = (
        Interview.objects.filter(
            action_item__application__project__organization=org,
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        )
        .select_related(
            "action_item__application__candidate",
            "action_item__application__project__client",
        )
    )
    actions = (
        ActionItem.objects.filter(
            application__project__organization=org,
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        )
        .exclude(action_type__code="interview_round")
        .select_related(
            "action_type",
            "application__project__client",
        )
    )

    if not scope_owner:
        interviews = interviews.filter(
            action_item__application__project__assigned_consultants=user
        )
        actions = actions.filter(assigned_to=user)

    events = []

    for iv in interviews:
        candidate = iv.action_item.application.candidate
        events.append({
            "scheduled_at": iv.scheduled_at,
            "label_color": "info",
            "title": f"{iv.round}차 면접",
            "subtitle": f"후보자: {candidate.name} · {iv.location or '-'}",
        })

    for ai in actions:
        code = ai.action_type.code
        color = "warning" if code in _CLIENT_FACING_CODES else "ink3"
        proj = ai.application.project
        client = proj.client
        events.append({
            "scheduled_at": ai.scheduled_at,
            "label_color": color,
            "title": ai.title,
            "subtitle": f"{proj.title} · {client.name}",
        })

    events.sort(key=lambda e: e["scheduled_at"])
    return events[:limit]
```

Update `get_dashboard_context`:
```python
        "weekly_schedule": _weekly_schedule(org, user, scope_owner),
```

- [ ] **Step 4: Replace template S3 Weekly (`dash_full.html:203-239`)**

Replace the weekly schedule `<div class="col-span-4">` content with:

```html
      <div class="col-span-4">
        <div class="eyebrow mb-4">Weekly Schedule</div>
        <div class="space-y-4">
          {% for ev in weekly_schedule %}
          <div class="bg-surface rounded-card shadow-card p-5">
            <div class="flex items-start justify-between">
              <div class="eyebrow eyebrow-ko {% if ev.label_color == 'info' %}!text-info{% elif ev.label_color == 'warning' %}!text-warning{% else %}!text-ink3{% endif %}">{{ ev.scheduled_at|date:"n월 j일 l · H:i" }}</div>
              <button class="text-faint hover:text-ink" type="button" aria-label="메뉴">
                <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
              </button>
            </div>
            <div class="mt-3 text-base font-semibold leading-snug">{{ ev.title }}</div>
            <div class="text-xs text-muted mt-1">{{ ev.subtitle }}</div>
          </div>
          {% empty %}
          <div class="bg-surface rounded-card shadow-card p-5">
            <div class="text-sm text-muted">이번 주 일정이 없습니다</div>
          </div>
          {% endfor %}
        </div>
      </div>
```

Note: Uses Django `|date:"n월 j일 l · H:i"` — `l` emits Korean weekday if `LANGUAGE_CODE="ko-kr"` (confirmed by codebase convention). If not translated, result like "월요일" may appear as "Monday"; check `settings.LANGUAGE_CODE` and adjust if needed (add `{% load i18n %}` and use `|date:"n월 j일 (l) · H:i"`).

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add projects/services/dashboard.py projects/templates/projects/partials/dash_full.html tests/test_dashboard_phase2a.py
git commit -m "feat(dashboard): S3 Weekly Schedule 실데이터

- _weekly_schedule(): Interview + ActionItem 이번 주 합집합, 시간 asc, 최대 5
- 라벨 색: Interview=info / 고객사 관련 action=warning / else=ink3
- 빈 상태 '이번 주 일정이 없습니다'
- 스코프: owner=전체, 그 외=본인 담당"
```

---

## Task 6: S3 Monthly Calendar

**Files:**
- Modify: `projects/services/dashboard.py`
- Modify: `projects/templates/projects/partials/dash_full.html:241-325`
- Modify: `tests/test_dashboard_phase2a.py`

**Semantics:**
- 이번 달 기준 7×N 그리드. 월의 1일이 속한 주의 월요일(한국식 주시작 일요일이면 → 일요일)부터 시작하도록 표시.
- 목업은 **일요일 시작** 주 (`일 월 화 수 목 금 토` 헤더). 일요일 시작으로 맞춤.
- 리스트 구조: `[{"date": int, "is_today": bool, "is_outside": bool, "event_label": str | None}, ...]` 총 42개 항목 (6주).
- `is_outside=True`: 이전/다음 달 날짜.
- `event_label` 규칙:
  1. 해당 날짜에 Interview N건 → `"인터뷰" if N==1 else f"인터뷰 {N}"`
  2. Interview 없고 ActionItem(scheduled_at, non-interview) M건 → `"일정" if M==1 else f"일정 {M}"`
  3. 둘 다 없으면 `None`
- 스코프 동일.

- [ ] **Step 1: Write failing test**

Append to `tests/test_dashboard_phase2a.py`:

```python
@pytest.mark.django_db
def test_s3_monthly_calendar_has_42_cells(owner_client):
    """S3 Monthly: 6주 × 7일 = 42 cal-day 셀."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert body.count('class="cal-day') == 42


@pytest.mark.django_db
def test_s3_monthly_today_class(owner_client):
    """S3 Monthly: 오늘 날짜 셀에 today 클래스."""
    today = timezone.now().day
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    # <div class="cal-day today"> ... <span class="tnum">{today}</span>
    assert f'class="cal-day today"' in body


@pytest.mark.django_db
def test_s3_monthly_interview_label(
    owner_client, org, client_obj, interview_type, consultant_user
):
    """S3 Monthly: 인터뷰가 있는 날짜에 '인터뷰' 라벨."""
    # 다음 주 월요일 (이번 달이라고 가정; 월말 엣지는 별도 테스트)
    now = timezone.now()
    target = now.replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    # skip if crossing month boundary
    if target.month != now.month:
        pytest.skip("month boundary edge case")

    cand = Candidate.objects.create(organization=org, name="홍길동")
    proj = Project.objects.create(organization=org, client=client_obj, title="P1")
    app = Application.objects.create(project=proj, candidate=cand)
    ai = ActionItem.objects.create(
        application=app, action_type=interview_type,
        title="1차 면접", scheduled_at=target,
    )
    Interview.objects.create(
        action_item=ai, round=1, scheduled_at=target,
        type="화상", location="Zoom",
    )

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert "인터뷰" in body  # label appeared
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v -k s3_monthly`
Expected: FAIL — cell count mismatch (hardcoded has ~42 but with old labels).

- [ ] **Step 3: Implement `_monthly_calendar` helper**

Add to `projects/services/dashboard.py`:

```python
from collections import defaultdict
from datetime import datetime as _dt


def _month_grid_start(year: int, month: int):
    """이번 달 1일이 속한 주의 일요일 (한국 달력 UI는 일요일 시작).

    Python weekday(): 월=0 … 일=6. 일요일 시작 기준 offset = (weekday+1) % 7.
    예: 1일이 월요일이면 offset=1 → 하루 전 일요일로 이동.
    """
    first = timezone.make_aware(_dt(year, month, 1, 0, 0, 0))
    offset = (first.weekday() + 1) % 7
    return first - timedelta(days=offset)


def _monthly_calendar(org, user, scope_owner):
    """S3 Monthly Calendar: 이번 달 6주 × 7일 = 42 셀.

    각 셀: {"date": int, "is_today": bool, "is_outside": bool,
            "event_label": str | None}
    """
    now = timezone.now()
    today = now.date()
    year, month = today.year, today.month

    grid_start = _month_grid_start(year, month)
    # 6주 * 7일 = 42일 범위
    grid_end = grid_start + timedelta(days=42)

    # 이벤트 집계: 날짜별 interview 개수, action 개수
    interview_by_date = defaultdict(int)
    action_by_date = defaultdict(int)

    interviews = Interview.objects.filter(
        action_item__application__project__organization=org,
        scheduled_at__gte=grid_start,
        scheduled_at__lt=grid_end,
    )
    actions = (
        ActionItem.objects.filter(
            application__project__organization=org,
            scheduled_at__gte=grid_start,
            scheduled_at__lt=grid_end,
        )
        .exclude(action_type__code="interview_round")
    )

    if not scope_owner:
        interviews = interviews.filter(
            action_item__application__project__assigned_consultants=user
        )
        actions = actions.filter(assigned_to=user)

    for iv in interviews.values_list("scheduled_at", flat=True):
        interview_by_date[timezone.localtime(iv).date()] += 1
    for at in actions.values_list("scheduled_at", flat=True):
        action_by_date[timezone.localtime(at).date()] += 1

    cells = []
    for i in range(42):
        d = (grid_start + timedelta(days=i)).date()
        is_outside = d.month != month
        is_today = d == today

        n_iv = interview_by_date.get(d, 0)
        n_act = action_by_date.get(d, 0)
        if n_iv:
            label = "인터뷰" if n_iv == 1 else f"인터뷰 {n_iv}"
        elif n_act:
            label = "일정" if n_act == 1 else f"일정 {n_act}"
        else:
            label = None

        cells.append({
            "date": d.day,
            "is_today": is_today,
            "is_outside": is_outside,
            "event_label": label,
        })

    return cells
```

Update `get_dashboard_context`:
```python
        "monthly_calendar": _monthly_calendar(org, user, scope_owner),
```

- [ ] **Step 4: Replace template S3 Monthly Calendar (`dash_full.html:241-325`)**

Replace the monthly calendar `<div class="col-span-8">` content (from `<div class="col-span-8">` line to closing `</div>` before `</section>`) with:

```html
      <div class="col-span-8">
        <div class="eyebrow mb-4">Monthly Schedule</div>
        <article class="bg-surface rounded-card shadow-card overflow-hidden">

          <div class="grid grid-cols-7 border-b border-hair">
            <div class="eyebrow eyebrow-ko text-center py-3 !text-red-600">일</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">월</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">화</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">수</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">목</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">금</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-blue-600">토</div>
          </div>

          <div class="grid grid-cols-7 [&>*]:-ml-0.5 [&>*]:-mt-0.5">
            {% for cell in monthly_calendar %}
            <div class="cal-day{% if cell.is_outside %} muted{% endif %}{% if cell.is_today %} today{% endif %}">
              <span class="tnum">{{ cell.date }}</span>
              {% if cell.event_label %}<div class="cal-event">{{ cell.event_label }}</div>{% endif %}
            </div>
            {% endfor %}
          </div>
        </article>
      </div>
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v`
Expected: all PASS (test_s3_monthly_interview_label may skip at month boundary).

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -x -q`
Expected: all green.

- [ ] **Step 7: Run linter/formatter**

Run: `uv run ruff check projects/services/dashboard.py tests/test_dashboard_phase2a.py && uv run ruff format projects/services/dashboard.py tests/test_dashboard_phase2a.py`
Expected: clean (or auto-fixed).

- [ ] **Step 8: Commit**

```bash
git add projects/services/dashboard.py projects/templates/projects/partials/dash_full.html tests/test_dashboard_phase2a.py
git commit -m "feat(dashboard): S3 Monthly Calendar 실데이터

- _monthly_calendar(): 이번 달 6주 × 7일 = 42 셀
- 각 날짜: Interview N건 '인터뷰 N' / ActionItem M건 '일정 M' / 없으면 라벨 없음
- 일요일 시작 그리드, today 클래스, outside 월 muted
- Phase 2a 완료"
```

---

## Post-Implementation Checklist

- [ ] `uv run pytest -x -q` 전체 그린
- [ ] `uv run ruff check .` 린트 통과
- [ ] 개발 서버는 사용자가 실행. UI 확인 경로: `http://localhost:8000/dashboard/`
- [ ] Phase 2b 작업 (S1-2 Revenue, S2-2 Recent Activity) 는 별도 스펙·플랜

---

## Self-Review Notes

1. **Spec coverage** — 6 tasks cover S1-1, S1-3, S2-1, S3 Weekly, S3 Monthly. S1-2 Revenue·S2-2 Recent Activity 은 Phase 2b 로 명시적 분리 (spec 과 일치).
2. **Permission scope** — `_scope_projects` 를 S1-1, S1-3, S2-1(except — always full), S3 양쪽 모두에서 사용. S2-1 만 스코프 무관(owner/consultant 양쪽 모두 전체 표시).
3. **Display name** — User 데이터 관행 확인은 Task 4 구현자가 첫 번째 실행 시 샘플 스캔 후 fallback 확정. 스펙의 "한글명 저장 관행" 오픈 이슈 해결.
4. **client-facing action_type codes** — `{"submit_to_client", "pre_meeting"}` 화이트리스트. 스펙의 두 번째 오픈 이슈 해결. 향후 추가되면 상수 수정.
