# Single-Tenant Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Organization`/`Membership` 멀티테넌시 전부 걷어내고 `User.level` + `is_superuser` 2축 권한 모델로 재편. 카카오 단일 로그인 + 승인 대기 플로우 + django-hijack 개발 UX.

**Architecture:** synco 를 single-tenant 로 전환한다. 각 회사는 별도 Docker Swarm 스택 + 별도 DB + 별도 도메인으로 배포하고, 앱 코드는 회사 개념을 모른다. 권한은 `User.level` (0=대기, 1=직원, 2=사장) 과 `is_superuser` (개발자) 두 축. 정보성 데이터(Candidate/Client/마스터)는 Level 1 이상 전체 조회, 업무성 데이터(Project/Application/ActionItem/Interview/Submission)는 Level 1 은 assigned 만 · Level 2+ 는 전체. 권한 체크는 `@level_required(n)` 데코레이터 + `scope_work_qs(qs, user)` 쿼리 헬퍼 2개로 통일.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Tailwind, pytest-django, Kakao OAuth, django-hijack 3.x, uv.

**Precondition:** 더미 데이터만 있는 상태. 마이그레이션·DB 전체 wipe 가능. 운영 서버 DB (49.247.45.243) 도 T8 에서 drop/create 대상.

---

## File Structure

### 신규 파일

| 경로 | 책임 |
|---|---|
| `accounts/services/__init__.py` | services 패키지 초기화 |
| `accounts/services/scope.py` | `scope_work_qs(qs, user)` — 업무성 쿼리셋 필터링 표준 헬퍼 |
| `accounts/management/__init__.py` | management 패키지 초기화 |
| `accounts/management/commands/__init__.py` | commands 패키지 초기화 |
| `accounts/management/commands/seed_superuser.py` | `SYNCO_SUPERUSER_EMAIL` 기반 슈퍼유저 1명 생성 |
| `accounts/templates/accounts/pending_approval.html` | Level 0 유저용 대기 페이지 (기존 파일 덮어쓰기) |
| `tests/accounts/test_level_required.py` | `level_required`, `superuser_required` 데코레이터 단위 테스트 |
| `tests/accounts/test_scope_work_qs.py` | `scope_work_qs` 헬퍼 단위 테스트 |
| `tests/accounts/test_kakao_flow.py` | 카카오 콜백 → 신규 유저 level=0, 승인 후 승격 시나리오 |
| `tests/accounts/test_hijack.py` | django-hijack 기본 동작 smoke |
| `tests/accounts/test_seed_superuser.py` | `seed_superuser` 커맨드 검증 |
| `docs/deploy/company-reset.md` | 운영 DB drop/create + `seed_superuser` 절차 |

### 수정 파일

| 경로 | 변경 요약 |
|---|---|
| `accounts/models.py` | `Organization`, `Membership`, `InviteCode` 클래스 삭제. `User` 에 `level`, `email` unique 추가 |
| `accounts/decorators.py` | `level_required(n)`, `superuser_required` 추가. `membership_required`, `role_required` 삭제 |
| `accounts/views.py` | 초대코드/rejected 관련 뷰 삭제. `kakao_callback` 단순화 (level=0). `pending_approval_page` 에 level 분기 |
| `accounts/views_org.py` | 파일 삭제 (초대코드 관리 UI) |
| `accounts/views_superadmin.py` | Level 2 유저 관리 UI 로 재작성 (Level 0 승급 포함) |
| `accounts/views_team.py` | Team 멤버 리스트 — `User.objects.filter(level__gte=1)` 기반으로 단순화 |
| `accounts/forms.py` | 초대코드 입력 폼 삭제 |
| `accounts/context_processors.py` | `membership` 컨텍스트 제거, `current_user_level` 만 노출 |
| `accounts/admin.py` | `Organization`/`Membership`/`InviteCode` 언레지스터. `User` admin 에 level 필드 노출 |
| `accounts/urls.py` | `/invite/`, `/rejected/` 라우트 삭제. `/login/` 은 카카오 전용 landing |
| `accounts/backends.py` | (변경 없음 — 이미 Kakao 백엔드) |
| `clients/models.py` | `Client.organization` 필드 삭제 |
| `clients/views.py` | `@membership_required` → `@level_required(1)`. 편집은 `@level_required(2)`. `organization` 필터 제거 |
| `clients/views_reference.py` | 동일 패턴 교체 |
| `clients/admin.py` | `organization` 관련 필드 참조 제거 |
| `candidates/models.py` | `Candidate.owned_by` FK 삭제 |
| `candidates/views_extension.py` | `organization` 필터 제거 |
| `projects/models.py` | `Project.organization`, `NewsSource.organization`, `ResumeUpload.organization` 삭제 |
| `projects/views.py` | 모든 `@membership_required` → `@level_required(1)`. `organization` 필터 제거. 업무 쿼리는 `scope_work_qs(qs, request.user)` 사용 |
| `projects/views_news.py`, `views_telegram.py`, `views_voice.py` | 동일 패턴 교체 |
| `projects/services/dashboard.py` | `get_dashboard_context(user)` 로 시그니처 단순화. `scope_owner = user.level >= 2 or user.is_superuser` |
| `projects/services/**/*.py` | `org`/`organization` 파라미터 및 필터 제거 |
| `projects/telegram/**/*.py` | 동일 |
| `projects/management/commands/seed_dummy_data.py` | Organization 생성 로직 제거, User 레벨 기반 시드 |
| `projects/management/commands/check_email_resumes.py` | organization 필터 제거 |
| `projects/management/commands/fetch_news.py` | organization 필터 제거 |
| `main/settings.py` | `INSTALLED_APPS` 에 `hijack`, `hijack.contrib.admin` 추가. `MIDDLEWARE` 에 `hijack.middleware.HijackUserMiddleware` 추가 |
| `main/urls.py` | `path("hijack/", include("hijack.urls"))` 추가 |
| `pyproject.toml` | `django-hijack` 의존성 추가 |
| `tests/conftest.py` | `org`/`user`/`other_user`/`other_org_user`/`client_company`/`project` fixture 전면 개편. Level 기반 fixture 도입 |
| `deploy.sh` | `--company=SLUG` 인자 파싱 스텁 추가 (동작은 단일 스택 유지) |

### 삭제 파일

| 경로 | 사유 |
|---|---|
| `accounts/views_org.py` | 초대코드·조직 관리 뷰 |
| `accounts/templates/accounts/invite_code.html` | 초대코드 입력 |
| `accounts/templates/accounts/rejected.html` | rejected 상태 페이지 |
| `accounts/templates/accounts/partials/org_invites.html` | 초대코드 관리 파셜 |
| `tests/accounts/test_rbac.py` | Membership role 기반 RBAC — `level_required` 테스트로 교체 |
| `tests/accounts/test_onboarding.py` | Membership 기반 온보딩 — 새 `test_kakao_flow.py` 로 교체 |
| `tests/accounts/test_org_management.py` | Organization 관리 UI |
| `tests/accounts/test_invite_code.py` | 초대코드 플로우 |
| `tests/accounts/test_nav_org.py` | Nav 조직 스위처 |
| `accounts/migrations/0001-0007*.py` | T8 에서 wipe |
| `clients/migrations/0001-0006*.py` | T8 에서 wipe |
| `candidates/migrations/0001-0022*.py` | T8 에서 wipe |
| `projects/migrations/0001-0005*.py` | T8 에서 wipe |
| `data_extraction/migrations/0001_initial.py` | T8 에서 wipe |

---

## Task Ordering Rationale

- **T1-T4** 는 기존 코드와 공존 가능한 추가 작업 (User 필드 추가, 데코레이터 추가, 새 로그인 플로우 준비, hijack 설치). 기존 Membership 코드는 그대로 두고 새 구조를 옆에 짓는다.
- **T5** 는 앱별로 뷰·서비스의 권한 레이어를 membership_required → level_required 로 갈아끼운다. 앱 단위 5 서브태스크 (T5a~T5e).
- **T6** 에서 Organization/Membership/InviteCode 모델과 관련 view/template/admin 을 드러낸다. T5 가 끝난 후라 참조가 없다.
- **T7** 에서 모델의 `organization` FK 필드 삭제.
- **T8** 에서 마이그레이션 wipe + 재생성 + 시드 커맨드.
- **T9** 에서 conftest + 남은 테스트 스위트 일괄 정비.
- **T10** 에서 Phase 2a 대시보드 코드 재연결.
- **T11** 는 deploy.sh 스텁 + 운영 배포 문서.
- **T12** 는 운영 DB 초기화 + 배포 (사용자 수동 승인 필요).

---

## Conventions

- 모든 테스트는 `pytest-django` + `Client.force_login(user)` 기반 실제 HTTP 호출. 내부 함수 직접 호출 금지 (기억: `feedback_realistic_testing.md`).
- 커밋 메시지: `feat(...):`, `refactor(...):`, `chore(...):`, `test(...):` prefix.
- `git add -A` 금지. 변경 파일을 명시적으로 add.
- 각 태스크는 마지막 스텝이 "commit". 다음 태스크는 clean working tree 에서 시작.

---

## Task 1: User.level 필드 추가 + 신규 fixture 도입

**목적:** `User` 모델에 `level` 필드를 비파괴적으로 추가한다. 기존 Membership 은 그대로 둔다. 테스트 conftest 에 새 fixture 를 추가하되 기존 fixture 도 유지.

**Files:**
- Modify: `accounts/models.py:11-28` (User 모델)
- Create migration: `accounts/migrations/0009_user_level.py` (auto-generated; Django picked 0009 because existing 0008_notificationpreference.py)
- Modify: `tests/conftest.py` (새 fixture 추가만)

- [ ] **Step 1: Write failing test for User.level default**

Create `tests/accounts/test_user_level_field.py`:

```python
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_new_user_defaults_to_level_0():
    u = User.objects.create_user(username="u1", password="x")
    assert u.level == 0


@pytest.mark.django_db
def test_user_level_choices_accepted():
    u = User.objects.create_user(username="u2", password="x", level=1)
    u.refresh_from_db()
    assert u.level == 1

    u.level = 2
    u.save()
    u.refresh_from_db()
    assert u.level == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_user_level_field.py -v`
Expected: FAIL with `AttributeError: 'User' object has no attribute 'level'` or migration error.

- [ ] **Step 3: Add level field to User**

Edit `accounts/models.py`. Inside `class User(AbstractUser):`, add after `push_subscription`:

```python
    class Level(models.IntegerChoices):
        PENDING = 0, "대기"
        STAFF = 1, "직원"
        BOSS = 2, "사장"

    level = models.IntegerField(
        choices=Level.choices,
        default=Level.PENDING,
    )
```

- [ ] **Step 4: Generate migration**

Run: `uv run python manage.py makemigrations accounts`
Expected output: `Migrations for 'accounts': accounts/migrations/0009_user_level.py`

- [ ] **Step 5: Apply migration**

Run: `uv run python manage.py migrate accounts`
Expected: `Applying accounts.0008_user_level... OK`

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/accounts/test_user_level_field.py -v`
Expected: 2 passed.

- [ ] **Step 7: Add new fixtures in conftest.py**

Edit `tests/conftest.py`. Append after existing fixtures:

```python
# --- Level-based fixtures (single-tenant refactor) ---


@pytest.fixture
def pending_user(db):
    return User.objects.create_user(
        username="pending_u", password="x", level=0
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff_u", password="x", level=1
    )


@pytest.fixture
def boss_user(db):
    return User.objects.create_user(
        username="boss_u", password="x", level=2
    )


@pytest.fixture
def dev_user(db):
    return User.objects.create_user(
        username="dev_u",
        password="x",
        level=2,
        is_superuser=True,
        is_staff=True,
    )


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def boss_client(client, boss_user):
    client.force_login(boss_user)
    return client


@pytest.fixture
def pending_client(client, pending_user):
    client.force_login(pending_user)
    return client


@pytest.fixture
def dev_client(client, dev_user):
    client.force_login(dev_user)
    return client
```

- [ ] **Step 8: Verify full suite still passes**

Run: `uv run pytest -x --ignore=tests/test_dashboard_phase2a.py 2>&1 | tail -20`
Expected: 기존 테스트 모두 통과 (신규 필드는 default 값이 있으므로 기존 코드 무영향).

- [ ] **Step 9: Commit**

```bash
git add accounts/models.py accounts/migrations/0009_user_level.py tests/conftest.py tests/accounts/test_user_level_field.py
git commit -m "$(cat <<'EOF'
feat(accounts): add User.level field (0=pending, 1=staff, 2=boss)

신규 권한 모델 도입 1단계. 기존 Membership 은 유지.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: level_required / superuser_required 데코레이터 + scope_work_qs 헬퍼

**목적:** 새 권한 체크의 3 개 프리미티브 (`level_required(n)`, `superuser_required`, `scope_work_qs(qs, user)`) 를 추가하고 단위 테스트. 기존 `membership_required` 는 유지.

**Files:**
- Create: `accounts/services/__init__.py`
- Create: `accounts/services/scope.py`
- Modify: `accounts/decorators.py` (함수 2개 추가)
- Create: `tests/accounts/test_level_required.py`
- Create: `tests/accounts/test_scope_work_qs.py`

- [ ] **Step 1: Write failing tests for level_required**

Create `tests/accounts/test_level_required.py`:

```python
import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path

from accounts.decorators import level_required, superuser_required


@level_required(1)
def staff_view(request):
    return HttpResponse("ok")


@level_required(2)
def boss_view(request):
    return HttpResponse("ok")


@superuser_required
def dev_view(request):
    return HttpResponse("ok")


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.mark.django_db
def test_pending_redirected_to_approval(rf, pending_user):
    req = rf.get("/")
    req.user = pending_user
    resp = staff_view(req)
    assert resp.status_code == 302
    assert resp["Location"].endswith("/accounts/pending/")


@pytest.mark.django_db
def test_staff_passes_level_1(rf, staff_user):
    req = rf.get("/")
    req.user = staff_user
    resp = staff_view(req)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_staff_forbidden_on_level_2(rf, staff_user):
    req = rf.get("/")
    req.user = staff_user
    resp = boss_view(req)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_boss_passes_level_2(rf, boss_user):
    req = rf.get("/")
    req.user = boss_user
    resp = boss_view(req)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_superuser_passes_all_levels(rf, dev_user):
    req = rf.get("/")
    req.user = dev_user
    assert staff_view(req).status_code == 200
    assert boss_view(req).status_code == 200
    assert dev_view(req).status_code == 200


@pytest.mark.django_db
def test_boss_blocked_from_superuser_view(rf, boss_user):
    req = rf.get("/")
    req.user = boss_user
    resp = dev_view(req)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/accounts/test_level_required.py -v`
Expected: FAIL — `ImportError: cannot import name 'level_required'`.

- [ ] **Step 3: Implement decorators**

Edit `accounts/decorators.py`. Replace entire file content with:

```python
"""RBAC decorators. Must be used after @login_required."""

from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


def _redirect_named(name, fallback):
    try:
        return redirect(reverse(name))
    except NoReverseMatch:
        return redirect(fallback)


def level_required(min_level):
    """Gate a view on User.level. Level 0 → pending page.

    Superusers bypass (treated as Level 2+).
    Insufficient level but authenticated → 403.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user

            if user.is_superuser:
                return view_func(request, *args, **kwargs)

            if user.level == 0:
                return _redirect_named(
                    "pending_approval", "/accounts/pending/"
                )

            if user.level < min_level:
                return HttpResponseForbidden(
                    "이 페이지에 접근할 권한이 없습니다."
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def superuser_required(view_func):
    """Allow only User.is_superuser. Others get 403."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden(
                "개발자 전용 페이지입니다."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


# Legacy — to be removed in T6 after all consumers migrate.
def membership_required(view_func):
    from accounts.models import Membership

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        try:
            membership = request.user.membership
        except Membership.DoesNotExist:
            return _redirect_named("invite_code", "/accounts/invite/")
        if membership.status == "pending":
            return _redirect_named(
                "pending_approval", "/accounts/pending/"
            )
        if membership.status == "rejected":
            return _redirect_named("rejected", "/accounts/rejected/")
        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*roles):
    from accounts.models import Membership

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                membership = request.user.membership
            except Membership.DoesNotExist:
                return _redirect_named("invite_code", "/accounts/invite/")
            if membership.status != "active":
                return _redirect_named(
                    "pending_approval", "/accounts/pending/"
                )
            if membership.role not in roles:
                return HttpResponseForbidden(
                    "이 페이지에 접근할 권한이 없습니다."
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
```

- [ ] **Step 4: Run level_required tests**

Run: `uv run pytest tests/accounts/test_level_required.py -v`
Expected: 6 passed.

- [ ] **Step 5: Write failing tests for scope_work_qs**

Create `tests/accounts/test_scope_work_qs.py`:

```python
import pytest

from accounts.services.scope import scope_work_qs
from projects.models import Project, ProjectStatus


@pytest.fixture
def projects_fixture(db, staff_user, boss_user):
    from clients.models import Client

    cli = Client.objects.create(name="Acme")
    p_assigned = Project.objects.create(
        client=cli, title="Own", status=ProjectStatus.OPEN, created_by=staff_user
    )
    p_assigned.assigned_consultants.add(staff_user)

    p_other = Project.objects.create(
        client=cli, title="Other", status=ProjectStatus.OPEN, created_by=boss_user
    )
    p_other.assigned_consultants.add(boss_user)
    return p_assigned, p_other


@pytest.mark.django_db
def test_staff_sees_only_assigned(staff_user, projects_fixture):
    p_assigned, p_other = projects_fixture
    qs = scope_work_qs(Project.objects.all(), staff_user)
    ids = set(qs.values_list("id", flat=True))
    assert p_assigned.id in ids
    assert p_other.id not in ids


@pytest.mark.django_db
def test_boss_sees_all(boss_user, projects_fixture):
    qs = scope_work_qs(Project.objects.all(), boss_user)
    assert qs.count() == 2


@pytest.mark.django_db
def test_superuser_sees_all(dev_user, projects_fixture):
    qs = scope_work_qs(Project.objects.all(), dev_user)
    assert qs.count() == 2


@pytest.mark.django_db
def test_pending_sees_nothing(pending_user, projects_fixture):
    qs = scope_work_qs(Project.objects.all(), pending_user)
    assert qs.count() == 0
```

- [ ] **Step 6: Run tests to verify failure**

Run: `uv run pytest tests/accounts/test_scope_work_qs.py -v`
Expected: FAIL — `ModuleNotFoundError: accounts.services.scope`.

- [ ] **Step 7: Implement scope_work_qs**

Create `accounts/services/__init__.py` (empty file):

```python
```

Create `accounts/services/scope.py`:

```python
"""Query scope helpers for work-type entities (Project, Application, ActionItem, ...)."""


def scope_work_qs(qs, user, assigned_field="assigned_consultants"):
    """Filter a work-entity queryset by the user's permission level.

    - Level 0 (pending): empty queryset.
    - Level 1 (staff): only rows where the user is in `assigned_field`.
    - Level 2+ or is_superuser: full queryset.
    """
    if user.is_superuser or user.level >= 2:
        return qs

    if user.level < 1:
        return qs.none()

    filter_kwargs = {assigned_field: user}
    return qs.filter(**filter_kwargs).distinct()
```

- [ ] **Step 8: Run scope_work_qs tests**

Run: `uv run pytest tests/accounts/test_scope_work_qs.py -v`
Expected: 4 passed.

- [ ] **Step 9: Commit**

```bash
git add accounts/decorators.py accounts/services/__init__.py accounts/services/scope.py tests/accounts/test_level_required.py tests/accounts/test_scope_work_qs.py
git commit -m "$(cat <<'EOF'
feat(accounts): level_required / superuser_required decorators + scope_work_qs helper

새 권한 체크 프리미티브. 기존 membership_required/role_required 는 T6 까지 유지.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 카카오 단일 로그인 + 승인 대기 페이지 재작성

**목적:** 카카오 외 로그인 경로 제거. `kakao_callback` 은 User 생성 시 `level=0` 기본값 사용. `pending_approval_page` 는 Membership 대신 `user.level` 기반으로 렌더. "메인화면으로 가기" 버튼은 `level >= 1` 일 때만 활성.

**Files:**
- Modify: `accounts/views.py:17-150` (home, invite_code_page, kakao_callback, pending_approval_page, rejected_page, landing_page 정리)
- Modify: `accounts/urls.py` (`/invite/`, `/rejected/`, `/chaconne67-login/`, `/ceo-login/` 삭제)
- Modify: `accounts/templates/accounts/pending_approval.html` (버튼 disable 분기)
- Create: `tests/accounts/test_kakao_flow.py`

- [ ] **Step 1: Write failing tests for new flow**

Create `tests/accounts/test_kakao_flow.py`:

```python
from unittest.mock import patch

import pytest
from django.urls import reverse

from accounts.models import User


@pytest.mark.django_db
def test_home_level_0_redirects_to_pending(pending_client):
    resp = pending_client.get(reverse("home"))
    assert resp.status_code == 302
    assert resp["Location"].endswith("/accounts/pending/")


@pytest.mark.django_db
def test_home_level_1_redirects_to_dashboard(staff_client):
    resp = staff_client.get(reverse("home"))
    assert resp.status_code == 302
    assert "/dashboard" in resp["Location"]


@pytest.mark.django_db
def test_pending_page_shows_disabled_button_for_level_0(pending_client):
    resp = pending_client.get(reverse("pending_approval"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "승인 요청이 관리자에게 전달" in body
    assert 'data-testid="enter-dashboard-btn"' in body
    assert "disabled" in body


@pytest.mark.django_db
def test_pending_page_button_enabled_after_promotion(client, pending_user):
    client.force_login(pending_user)
    pending_user.level = 1
    pending_user.save()

    resp = client.get(reverse("pending_approval"))
    body = resp.content.decode()
    assert 'data-testid="enter-dashboard-btn"' in body
    # Disabled-specific marker should NOT be present on active button
    assert "opacity-50" not in body or "disabled" not in body


@pytest.mark.django_db
def test_invite_code_url_removed(client):
    from django.urls import NoReverseMatch
    with pytest.raises(NoReverseMatch):
        reverse("invite_code")


@pytest.mark.django_db
@patch("accounts.views.httpx.get")
@patch("accounts.views.httpx.post")
def test_kakao_callback_creates_level_0_user(mock_post, mock_get, client):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json = lambda: {"access_token": "T"}
    mock_get.return_value.status_code = 200
    mock_get.return_value.json = lambda: {
        "id": 12345,
        "kakao_account": {"profile": {"nickname": "홍길동"}},
    }

    resp = client.get(reverse("kakao_callback") + "?code=abc")

    assert resp.status_code == 302
    assert resp["Location"].endswith("/")  # home redirect

    u = User.objects.get(kakao_id=12345)
    assert u.level == 0
    assert u.is_superuser is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/accounts/test_kakao_flow.py -v`
Expected: multiple failures (home still checks Membership, pending page has no disabled state, invite_code URL still exists).

- [ ] **Step 3: Rewrite home/pending views**

Edit `accounts/views.py`. Replace lines 16-144 (home, invite_code_page, `_notify_owners_new_pending`, pending_approval_page, rejected_page) with:

```python
@login_required
def home(request):
    """Root redirect -- route by user.level."""
    user = request.user
    if user.is_superuser or user.level >= 1:
        return redirect("dashboard")
    return redirect("pending_approval")


@login_required
def pending_approval_page(request):
    """Level 0 대기 페이지. Level 1 이상이면 버튼 활성화 상태로 렌더."""
    user = request.user
    activated = user.is_superuser or user.level >= 1
    return render(
        request,
        "accounts/pending_approval.html",
        {"activated": activated},
    )
```

Also remove `InviteCode, Membership` from the top-level import on line 13 — leave `User` only:

```python
from .models import User
```

- [ ] **Step 4: Update pending_approval template**

Overwrite `accounts/templates/accounts/pending_approval.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="max-w-md mx-auto py-16 text-center space-y-6">
  <h1 class="text-2xl font-bold">승인 대기</h1>
  <p class="text-ink3">
    승인 요청이 관리자에게 전달되었습니다.<br>
    확인 후 이용하실 수 있습니다.
  </p>

  {% if activated %}
    <a href="{% url 'dashboard' %}"
       data-testid="enter-dashboard-btn"
       class="inline-block px-6 py-3 bg-accent text-white rounded-lg font-medium">
      메인화면으로 가기
    </a>
  {% else %}
    <button type="button"
            data-testid="enter-dashboard-btn"
            class="inline-block px-6 py-3 bg-line text-ink3 rounded-lg font-medium opacity-50 cursor-not-allowed"
            disabled>
      메인화면으로 가기
    </button>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Simplify kakao_callback**

Edit `accounts/views.py:163-208` (kakao_callback). Change the User.objects.get_or_create block so defaults do not set membership/org. The existing code already creates User only; just ensure it does not touch Membership:

The existing lines 197-204 are already correct:

```python
user, created = User.objects.get_or_create(
    kakao_id=kakao_id,
    defaults={
        "username": f"kakao_{kakao_id}",
        "first_name": profile.get("nickname", ""),
    },
)
```

New User gets `level=0` from the field default. No change needed to this block. Confirm no Membership creation follows.

- [ ] **Step 6: Drop invite/rejected/password-login URLs**

Edit `accounts/urls.py`. Replace entire file:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("accounts/login/", views.landing_page, name="landing"),
    path("accounts/kakao/login/", views.kakao_login, name="kakao_login"),
    path("accounts/kakao/callback/", views.kakao_callback, name="kakao_callback"),
    path("accounts/pending/", views.pending_approval_page, name="pending_approval"),

    path("accounts/settings/", views.settings_page, name="settings"),
    path("accounts/settings/profile/", views.settings_profile, name="settings_profile"),
    path("accounts/settings/email/", views.settings_email, name="settings_email"),
    path(
        "accounts/settings/notify/", views.settings_notify, name="settings_notify"
    ),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),

    path("accounts/email/connect/", views.email_connect, name="email_connect"),
    path("accounts/email/callback/", views.email_oauth_callback, name="email_callback"),
    path("accounts/email/settings/", views.email_settings, name="email_settings"),
    path("accounts/email/disconnect/", views.email_disconnect, name="email_disconnect"),
]
```

- [ ] **Step 7: Remove dead views in views.py**

Edit `accounts/views.py`. Delete the following functions (they are no longer referenced after urls.py change):

- `staff_login_page` (line 354)
- `ceo_login_page` (line 384)
- `invite_code_page` (if any remnant)
- `rejected_page` (if any remnant)
- `_notify_owners_new_pending`

Also remove `authenticate` from the top import (line 5) since password login is gone:

```python
from django.contrib.auth import login, logout
```

- [ ] **Step 8: Run kakao_flow tests**

Run: `uv run pytest tests/accounts/test_kakao_flow.py -v`
Expected: 6 passed.

- [ ] **Step 9: Run full suite — expect old Membership tests still pass (legacy not removed yet)**

Run: `uv run pytest --ignore=tests/accounts/test_invite_code.py --ignore=tests/accounts/test_org_management.py --ignore=tests/accounts/test_onboarding.py --ignore=tests/accounts/test_nav_org.py --ignore=tests/accounts/test_rbac.py -x 2>&1 | tail -10`
Expected: pass (old invite/org tests are excluded because they reference URLs we just removed; they will be deleted in T9).

- [ ] **Step 10: Commit**

```bash
git add accounts/views.py accounts/urls.py accounts/templates/accounts/pending_approval.html tests/accounts/test_kakao_flow.py
git commit -m "$(cat <<'EOF'
feat(accounts): 카카오 단일 로그인 + Level 기반 승인 대기 페이지

- home/pending_approval 을 user.level 기반으로 재작성
- 초대코드/rejected/password-login URL 제거
- 대기 페이지 "메인화면으로 가기" 버튼은 level>=1 일 때만 활성

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: django-hijack 통합

**목적:** 슈퍼유저가 `/admin` 에서 Level 1/2 테스트 계정으로 임팩트 없이 로그인 전환.

**Files:**
- Modify: `pyproject.toml` (django-hijack 추가)
- Modify: `main/settings.py` (INSTALLED_APPS, MIDDLEWARE)
- Modify: `main/urls.py`
- Create: `tests/accounts/test_hijack.py`

- [ ] **Step 1: Write failing hijack smoke test**

Create `tests/accounts/test_hijack.py`:

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_hijack_urls_registered(client):
    url = reverse("hijack:acquire")
    assert url.startswith("/hijack/")


@pytest.mark.django_db
def test_superuser_can_hijack_staff_user(client, dev_user, staff_user):
    client.force_login(dev_user)

    resp = client.post(
        reverse("hijack:acquire"),
        {"user_pk": str(staff_user.pk), "next": "/"},
    )
    assert resp.status_code == 302

    whoami = client.get("/")
    session_user_pk = client.session.get("_auth_user_id")
    assert str(session_user_pk) == str(staff_user.pk)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/accounts/test_hijack.py -v`
Expected: FAIL — `NoReverseMatch: 'hijack' is not a registered namespace`.

- [ ] **Step 3: Install django-hijack**

Run: `uv add django-hijack`
Expected: `pyproject.toml` updated, `uv.lock` regenerated.

- [ ] **Step 4: Add to INSTALLED_APPS and MIDDLEWARE**

Edit `main/settings.py`. In `INSTALLED_APPS` list, add `"hijack"` and `"hijack.contrib.admin"` after `"django.contrib.admin"`:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "hijack",
    "hijack.contrib.admin",
    # ... rest of existing entries
]
```

In `MIDDLEWARE`, add `"hijack.middleware.HijackUserMiddleware"` after Django's `AuthenticationMiddleware`:

```python
MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "hijack.middleware.HijackUserMiddleware",
    # ...
]
```

- [ ] **Step 5: Include hijack URLs**

Edit `main/urls.py`. In `urlpatterns`, add before other app includes:

```python
from django.urls import include, path

urlpatterns = [
    path("hijack/", include("hijack.urls")),
    # ... existing entries
]
```

- [ ] **Step 6: Run hijack tests**

Run: `uv run pytest tests/accounts/test_hijack.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock main/settings.py main/urls.py tests/accounts/test_hijack.py
git commit -m "$(cat <<'EOF'
feat(deps): integrate django-hijack for dev user-switch testing

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 앱별 뷰·서비스 권한 레이어 교체

이 태스크는 규모가 커서 앱 단위 5 개 서브태스크로 분할한다. 각 서브태스크는 독립 커밋.

### Task 5a: clients 앱 전환

**Files:**
- Modify: `clients/views.py:60,90,138,160` (4 개 데코레이터)
- Modify: `clients/views_reference.py:67,77,208,234,402,428,549` (7 개 데코레이터)
- Modify: `tests/test_clients_views_list.py`, `test_clients_views_detail.py`, `test_clients_views_form.py`, `test_clients_views_delete.py`, `test_clients_create.py` (Membership fixture → level fixture)

- [ ] **Step 1: Replace decorators in clients/views.py**

Edit `clients/views.py`. Change import line (top):

```python
from accounts.decorators import level_required
```

Replace each `@membership_required` on list/detail (line 60, 90): use `@level_required(1)`. On create/edit/delete (line 138, 160): use `@level_required(2)`.

Remove any `organization` filter from querysets: e.g. `Client.objects.filter(organization=request.user.membership.organization)` → `Client.objects.all()`.

- [ ] **Step 2: Same for clients/views_reference.py**

Edit `clients/views_reference.py`. Replace 7 decorators (list = `level_required(1)`, edit/delete = `level_required(2)`). Drop organization filters.

- [ ] **Step 3: Update clients tests to use new fixtures**

Edit `tests/test_clients_views_list.py`. Replace `org`, `owner`, `owner_client` fixtures (lines 9-25) with imports of `boss_client`, `staff_client` from conftest:

```python
import pytest
from django.urls import reverse

from clients.models import Client, IndustryCategory
from projects.models import Project


@pytest.mark.django_db
def test_list_renders_header_and_empty_state(boss_client):
    resp = boss_client.get(reverse("clients:client_list"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Clients" in body
    assert "등록된 고객사" in body


@pytest.mark.django_db
def test_list_renders_cards(db, boss_client):
    Client.objects.create(
        name="SKBP", industry=IndustryCategory.BIO_PHARMA.value
    )
    resp = boss_client.get(reverse("clients:client_list"))
    assert "SKBP" in resp.content.decode()


@pytest.mark.django_db
def test_list_category_filter(db, boss_client):
    Client.objects.create(name="BioFirm", industry=IndustryCategory.BIO_PHARMA.value)
    Client.objects.create(name="TechCorp", industry=IndustryCategory.IT_SW.value)
    resp = boss_client.get(reverse("clients:client_list") + "?cat=BIO_PHARMA")
    body = resp.content.decode()
    assert "BioFirm" in body
    assert "TechCorp" not in body


@pytest.mark.django_db
def test_list_size_filter(db, boss_client):
    Client.objects.create(name="Big", size="대기업")
    Client.objects.create(name="Small", size="중소")
    resp = boss_client.get(reverse("clients:client_list") + "?size=대기업")
    body = resp.content.decode()
    assert "Big" in body
    assert "Small" not in body


@pytest.mark.django_db
def test_list_page_endpoint_returns_next_cards(db, boss_client):
    for i in range(10):
        Client.objects.create(name=f"C{i:02d}")
    resp = boss_client.get(reverse("clients:client_list_page") + "?page=2")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert body.count("client-card") == 1


@pytest.mark.django_db
def test_list_active_count_shown(db, boss_client, boss_user):
    from projects.models import ProjectStatus

    c = Client.objects.create(name="A")
    Project.objects.create(client=c, title="P", status=ProjectStatus.OPEN, created_by=boss_user)
    resp = boss_client.get(reverse("clients:client_list"))
    body = resp.content.decode()
    assert "1" in body
    assert "Active" in body


@pytest.mark.django_db
def test_staff_cannot_see_add_button(staff_client):
    resp = staff_client.get(reverse("clients:client_list"))
    assert "Add Client" not in resp.content.decode()
```

Apply equivalent rewrites to `test_clients_views_detail.py`, `test_clients_views_form.py`, `test_clients_views_delete.py`, `test_clients_create.py`, `test_clients_models.py`, `test_clients_queries.py`, `test_clients_templatetags.py`: remove `org` fixture usage, drop `organization=org` from `Client.objects.create(...)` and `Project.objects.create(...)` — those are still keyword args until T7, but the field should be passed as `organization=None` fallback to keep schema happy until T7.

Actually — the FK is NOT NULL on Client right now, so we can't drop it mid-task. Keep `organization=org` in tests for 5a only. The simpler pattern: update `org` fixture to a locally defined helper that still creates Organization; new fixtures (`boss_client`) don't need `org`. Example:

```python
@pytest.fixture
def legacy_org(db):
    """Temporary shim until T7 drops organization FK."""
    from accounts.models import Organization
    return Organization.objects.create(name="Legacy")


@pytest.mark.django_db
def test_list_renders_cards(db, boss_client, legacy_org):
    Client.objects.create(name="SKBP", organization=legacy_org, industry=IndustryCategory.BIO_PHARMA.value)
    ...
```

Use this shim pattern across 5a/5b/5c/5d until T7 drops the FK.

- [ ] **Step 4: Run clients tests**

Run: `uv run pytest tests/test_clients_views_list.py tests/test_clients_views_detail.py tests/test_clients_views_form.py tests/test_clients_views_delete.py tests/test_clients_create.py tests/test_clients_models.py tests/test_clients_queries.py tests/test_clients_templatetags.py -v 2>&1 | tail -30`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clients/views.py clients/views_reference.py tests/test_clients_*.py
git commit -m "$(cat <<'EOF'
refactor(clients): level_required 데코레이터 + organization 필터 제거

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 5b: candidates 앱 전환

**Files:**
- Modify: `candidates/views_extension.py` (데코레이터 + organization 필터)
- Modify: tests that touch candidates

- [ ] **Step 1: Inspect candidates views for membership_required**

Run: `uv run grep -n "membership_required\|organization" candidates/views_extension.py | head -30`

- [ ] **Step 2: Replace decorators**

In `candidates/views_extension.py`, import `level_required` and swap every `@membership_required` → `@level_required(1)` (candidate browsing is read-only for staff). Drop any `Candidate.objects.filter(owned_by=...)` (legacy scope); replace with `Candidate.objects.all()`.

- [ ] **Step 3: Run candidate tests**

Run: `uv run pytest tests/test_candidates*.py -v 2>&1 | tail -20`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add candidates/views_extension.py tests/test_candidates*.py
git commit -m "$(cat <<'EOF'
refactor(candidates): level_required 데코레이터 + owned_by 필터 제거

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 5c: projects 앱 views 전환

**Files:**
- Modify: `projects/views.py` (50+ 데코레이터)
- Modify: `projects/views_news.py`, `projects/views_telegram.py`, `projects/views_voice.py`

- [ ] **Step 1: Swap all decorators in projects/views.py**

Use search-and-replace pattern. Edit `projects/views.py`:

Add import at top:

```python
from accounts.decorators import level_required
```

Replace every `@membership_required` → `@level_required(1)` across all 52 occurrences.

For each view that does `request.user.membership.organization` filtering:
- `Project.objects.filter(organization=...)` → `scope_work_qs(Project.objects.all(), request.user)`
- `Application.objects.filter(project__organization=...)` → `scope_work_qs(Application.objects.all(), request.user, assigned_field="project__assigned_consultants")`
- Same pattern for ActionItem (`assigned_field="assigned_to"`), Interview, Submission.

Import at top: `from accounts.services.scope import scope_work_qs`.

Remove `membership = request.user.membership` / `organization = membership.organization` lines.

- [ ] **Step 2: Swap decorators in views_news.py / views_telegram.py / views_voice.py**

Same pattern. Edit each file to replace decorator + drop organization filter.

- [ ] **Step 3: Run projects views tests**

Run: `uv run pytest tests/test_views*.py tests/test_projects*.py -v 2>&1 | tail -30`
Expected: pass (tests using `user`/`owner_client` still work because those fixtures still exist alongside new ones).

- [ ] **Step 4: Commit**

```bash
git add projects/views.py projects/views_news.py projects/views_telegram.py projects/views_voice.py
git commit -m "$(cat <<'EOF'
refactor(projects): level_required + scope_work_qs 전면 교체 (views)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 5d: projects 앱 services/telegram/management 전환

**Files:**
- Modify: `projects/services/dashboard.py` (별도 Task 10 에서 상세화, 여기서는 서명만 변경)
- Modify: `projects/services/resume/identity.py`
- Modify: `projects/services/voice/*.py`
- Modify: `projects/services/notification.py`
- Modify: `projects/services/email/*.py`
- Modify: `projects/services/candidate_matching.py`
- Modify: `projects/telegram/*.py`
- Modify: `projects/management/commands/check_email_resumes.py`, `fetch_news.py`, `seed_dummy_data.py`

- [ ] **Step 1: Find every service function with `org` / `organization` parameter**

Run: `uv run grep -n "def .*org\|def .*organization\|\.organization" projects/services/ -r | head -50`

- [ ] **Step 2: Drop the parameter + organization-based filter**

For each service function:
- Signature: remove `org` / `organization` parameter
- Body: remove `.filter(organization=org)` clauses
- Callers: update

Do the same for `projects/telegram/auth.py`, `handlers.py`. Telegram auth resolves user by phone/chat_id — no org filter needed.

For `projects/management/commands/seed_dummy_data.py`: remove `Organization.objects.create(...)` + `Membership.objects.create(...)` blocks. Seed should create a few Users at level=2 and level=1 directly.

For `check_email_resumes.py`, `fetch_news.py`: drop the per-org loop; run single-tenant.

- [ ] **Step 3: Run services tests**

Run: `uv run pytest tests/test_services*.py tests/test_voice*.py tests/test_email*.py -v 2>&1 | tail -30`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add projects/services/ projects/telegram/ projects/management/commands/
git commit -m "$(cat <<'EOF'
refactor(projects): drop organization from services/telegram/commands

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 5e: accounts 남은 엔드포인트 전환

**Files:**
- Modify: `accounts/views.py` (settings, email_connect, logout, etc.)
- Modify: `accounts/views_superadmin.py` (Level 0 승인 UI 로 재작성)
- Modify: `accounts/views_team.py` (User.level 기반 리스트)
- Modify: `accounts/context_processors.py`
- Modify: `accounts/forms.py`

- [ ] **Step 1: Swap decorators in accounts/views.py remaining endpoints**

Settings/email 뷰들은 `@login_required` + `@level_required(1)` 조합.

- [ ] **Step 2: Rewrite views_superadmin.py**

Replace with Level 2 전용 유저 관리 페이지:

```python
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from accounts.decorators import level_required
from accounts.models import User


@login_required
@level_required(2)
def pending_users_list(request):
    users = User.objects.filter(level=0).order_by("-date_joined")
    return render(
        request,
        "accounts/superadmin/pending_users.html",
        {"users": users},
    )


@login_required
@level_required(2)
@require_POST
def approve_user(request, user_id):
    new_level = int(request.POST.get("level", 1))
    if new_level not in (1, 2):
        new_level = 1
    User.objects.filter(pk=user_id, level=0).update(level=new_level)
    return redirect("pending_users_list")
```

- [ ] **Step 3: Rewrite views_team.py**

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import level_required
from accounts.models import User


@login_required
@level_required(1)
def team_list(request):
    members = User.objects.filter(level__gte=1).order_by("level", "date_joined")
    return render(request, "accounts/team_list.html", {"members": members})
```

- [ ] **Step 4: Simplify context_processors.py**

Edit `accounts/context_processors.py`:

```python
def rbac_context(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"current_user_level": None, "is_superuser": False}
    return {
        "current_user_level": user.level,
        "is_superuser": user.is_superuser,
    }
```

Register in `main/settings.py` `TEMPLATES.OPTIONS.context_processors` (replace previous `accounts.context_processors.membership_context` if present).

- [ ] **Step 5: Drop invite form in forms.py**

Delete `InviteCodeForm`, `AcceptInviteForm`, and any `OrganizationForm` classes from `accounts/forms.py`. Keep profile/email forms only.

- [ ] **Step 6: Run accounts tests**

Run: `uv run pytest tests/accounts/ --ignore=tests/accounts/test_invite_code.py --ignore=tests/accounts/test_org_management.py --ignore=tests/accounts/test_onboarding.py --ignore=tests/accounts/test_nav_org.py --ignore=tests/accounts/test_rbac.py -v 2>&1 | tail -30`
Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add accounts/views.py accounts/views_superadmin.py accounts/views_team.py accounts/context_processors.py accounts/forms.py main/settings.py
git commit -m "$(cat <<'EOF'
refactor(accounts): 남은 엔드포인트를 level_required 로 전환

- superadmin: Level 0 유저 승인 UI
- team: User.level 기반 리스트
- context_processor: current_user_level / is_superuser 만 노출

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Organization / Membership / InviteCode 모델 삭제

**목적:** T5 가 끝났으므로 모든 참조가 사라졌다. 모델·뷰·템플릿·admin·초대 플로우 관련 파일을 일괄 삭제.

**Files:**
- Delete: `accounts/views_org.py`
- Delete: `accounts/templates/accounts/invite_code.html`, `accounts/templates/accounts/rejected.html`, `accounts/templates/accounts/partials/org_invites.html`
- Modify: `accounts/models.py` (Organization, Membership, InviteCode 클래스 삭제)
- Modify: `accounts/admin.py` (언레지스터 + User admin 에 level 노출)
- Modify: `accounts/decorators.py` (legacy `membership_required`, `role_required` 삭제)
- Modify: `accounts/urls.py` (invite/rejected 라우트는 T3 에서 이미 제거)

- [ ] **Step 1: Verify no more references**

Run: `uv run grep -rn "Membership\|Organization\|InviteCode" --include="*.py" /home/work/synco 2>&1 | grep -v "migrations\|tests/\|accounts/models.py\|accounts/admin.py\|accounts/decorators.py\|accounts/__pycache__" | head -30`
Expected: output empty (outside of models/admin/decorators and tests, no consumer references).

If any remain (beyond tests, which are rewritten in T9), fix them before proceeding.

- [ ] **Step 2: Delete org views + templates**

Run:

```bash
rm accounts/views_org.py
rm accounts/templates/accounts/invite_code.html
rm accounts/templates/accounts/rejected.html
rm accounts/templates/accounts/partials/org_invites.html
```

- [ ] **Step 3: Drop classes from accounts/models.py**

Edit `accounts/models.py`. Delete:
- `class Organization(BaseModel)` (lines 30-52)
- `class Membership(BaseModel)` (lines 55-91)
- `class InviteCode(BaseModel)` (lines 94-159)

Also drop the unused `import secrets, string` if no other class needs them.

- [ ] **Step 4: Remove admin registrations**

Edit `accounts/admin.py`. Delete the Organization/Membership/InviteCode admin classes and `admin.site.register` calls (lines 20-47).

Add level to User admin fieldsets:

```python
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = ("username", "email", "level", "is_superuser", "date_joined")
    list_filter = ("level", "is_superuser")
    fieldsets = DefaultUserAdmin.fieldsets + (
        ("synco", {"fields": ("level", "kakao_id", "phone")}),
    )
```

- [ ] **Step 5: Remove legacy decorators**

Edit `accounts/decorators.py`. Delete `membership_required` and `role_required` functions (the whole sections added in T2 as shims).

- [ ] **Step 6: Run full suite minus deleted tests**

Run: `uv run pytest --ignore=tests/accounts/test_invite_code.py --ignore=tests/accounts/test_org_management.py --ignore=tests/accounts/test_onboarding.py --ignore=tests/accounts/test_nav_org.py --ignore=tests/accounts/test_rbac.py -x 2>&1 | tail -20`
Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add accounts/models.py accounts/admin.py accounts/decorators.py
git add -u accounts/views_org.py accounts/templates/accounts/invite_code.html accounts/templates/accounts/rejected.html accounts/templates/accounts/partials/org_invites.html
git commit -m "$(cat <<'EOF'
refactor(accounts): Organization/Membership/InviteCode 완전 제거

- 모델·admin·views_org·초대 템플릿·legacy 데코레이터 삭제
- User admin 에 level 필드 노출

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 모델의 organization FK 필드 제거

**목적:** 각 모델에서 `organization` FK 필드를 삭제. 아직 마이그레이션은 건드리지 않음 (T8 에서 wipe + regenerate).

**Files:**
- Modify: `clients/models.py:44` (Client.organization)
- Modify: `projects/models.py:167, 1181, 1296` (Project.organization, NewsSource.organization, ResumeUpload.organization)
- Modify: `candidates/models.py:360` (Candidate.owned_by)

- [ ] **Step 1: Drop Client.organization**

Edit `clients/models.py`. Find the `organization = models.ForeignKey(...)` line (~line 44) and delete it. Also drop the `from accounts.models import Organization` import if no longer needed.

- [ ] **Step 2: Drop Project/NewsSource/ResumeUpload organization**

Edit `projects/models.py`. Remove each `organization = models.ForeignKey(Organization, ...)` line. Drop the Organization import at top.

- [ ] **Step 3: Drop Candidate.owned_by**

Edit `candidates/models.py`. Remove `owned_by = models.ForeignKey(Organization, ...)` line.

- [ ] **Step 4: Remove lingering legacy_org shim fixtures**

Edit test files that still reference `legacy_org` fixture (added in T5). Remove the fixture definition and drop `organization=legacy_org` kwargs from `Client.objects.create(...)` / `Project.objects.create(...)` calls.

Search: `uv run grep -rn "legacy_org\|organization=org" tests/ | head -30`

For each match, delete the fixture definition and the kwarg.

- [ ] **Step 5: Run full suite (pre-migration — expect errors until T8)**

Run: `uv run pytest -x 2>&1 | tail -10`
Expected: failure due to schema mismatch (DB still has organization columns). That's fine — T8 resets.

- [ ] **Step 6: Commit**

```bash
git add clients/models.py projects/models.py candidates/models.py tests/
git commit -m "$(cat <<'EOF'
refactor: drop organization FK from Client/Project/NewsSource/ResumeUpload/Candidate

이 커밋 후 DB 스키마는 일시 불일치. T8 에서 마이그레이션 재생성.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 마이그레이션 wipe + 재생성 + seed 커맨드

**목적:** 각 앱의 `migrations/*.py` 를 삭제 후 `makemigrations` 로 fresh 0001_initial 생성. dev DB 초기화. `seed_superuser` 커맨드 + ActionType 데이터 마이그레이션 추가.

**Files:**
- Delete: `accounts/migrations/0001-0008*.py`, `clients/migrations/0001-0006*.py`, `candidates/migrations/0001-0022*.py`, `projects/migrations/0001-0005*.py`, `data_extraction/migrations/0001_initial.py`
- Create: `accounts/management/__init__.py`, `accounts/management/commands/__init__.py`
- Create: `accounts/management/commands/seed_superuser.py`
- Create (auto): `accounts/migrations/0001_initial.py`, `clients/migrations/0001_initial.py`, 등
- Create: `projects/migrations/0002_seed_actiontypes.py` (데이터 마이그레이션)
- Create: `tests/accounts/test_seed_superuser.py`

- [ ] **Step 1: Write failing test for seed_superuser**

Create `tests/accounts/test_seed_superuser.py`:

```python
import pytest
from django.core.management import call_command

from accounts.models import User


@pytest.mark.django_db
def test_seed_superuser_creates_user(settings):
    settings.SYNCO_SUPERUSER_EMAIL = "chaconne67@gmail.com"
    call_command("seed_superuser")
    u = User.objects.get(email="chaconne67@gmail.com")
    assert u.level == 2
    assert u.is_superuser is True
    assert u.is_staff is True


@pytest.mark.django_db
def test_seed_superuser_is_idempotent(settings):
    settings.SYNCO_SUPERUSER_EMAIL = "chaconne67@gmail.com"
    call_command("seed_superuser")
    call_command("seed_superuser")
    assert User.objects.filter(email="chaconne67@gmail.com").count() == 1
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/accounts/test_seed_superuser.py -v`
Expected: FAIL — `CommandError: Unknown command 'seed_superuser'`.

- [ ] **Step 3: Create management command**

Create `accounts/management/__init__.py` and `accounts/management/commands/__init__.py` (both empty).

Create `accounts/management/commands/seed_superuser.py`:

```python
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Ensure SYNCO_SUPERUSER_EMAIL user exists with level=2 and is_superuser=True."

    def handle(self, *args, **options):
        email = getattr(settings, "SYNCO_SUPERUSER_EMAIL", None)
        if not email:
            raise CommandError("SYNCO_SUPERUSER_EMAIL is not configured.")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email.split("@")[0],
                "level": 2,
                "is_superuser": True,
                "is_staff": True,
            },
        )
        if not created:
            user.level = 2
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["level", "is_superuser", "is_staff"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser ensured: {user.email} "
                f"(level={user.level}, is_superuser={user.is_superuser})"
            )
        )
```

- [ ] **Step 4: Add SYNCO_SUPERUSER_EMAIL to settings**

Edit `main/settings.py`. Add:

```python
SYNCO_SUPERUSER_EMAIL = os.environ.get("SYNCO_SUPERUSER_EMAIL", "chaconne67@gmail.com")
```

- [ ] **Step 5: Delete all migration files**

Run:

```bash
find accounts/migrations clients/migrations candidates/migrations projects/migrations data_extraction/migrations -name "*.py" -not -name "__init__.py" -delete
```

Verify: `ls accounts/migrations/ clients/migrations/ candidates/migrations/ projects/migrations/ data_extraction/migrations/`
Expected: only `__init__.py` per directory.

- [ ] **Step 6: Reset dev DB**

Run: `docker compose down -v && docker compose up -d`
Expected: volume destroyed and recreated.

Wait for postgres ready:

```bash
until docker compose exec -T db pg_isready -U synco; do sleep 1; done
```

- [ ] **Step 7: Regenerate migrations**

Run: `uv run python manage.py makemigrations accounts clients candidates projects data_extraction`
Expected: each app writes a fresh `0001_initial.py`.

- [ ] **Step 8: Apply migrations**

Run: `uv run python manage.py migrate`
Expected: all migrations applied OK.

- [ ] **Step 9: Add ActionType seed data migration**

First check current ActionType seed logic. Run:

```bash
uv run grep -l "ActionType" projects/migrations/0001_initial.py projects/models.py | head
```

Create `projects/migrations/0002_seed_actiontypes.py`:

```python
from django.db import migrations


ACTION_TYPES = [
    ("reach_out", "첫 연락", "consultant"),
    ("followup", "후속 연락", "consultant"),
    ("interview_schedule", "인터뷰 조율", "consultant"),
    ("submit_to_client", "고객사 제출", "client"),
    ("confirm_hire", "채용 확정", "client"),
]


def forwards(apps, schema_editor):
    ActionType = apps.get_model("projects", "ActionType")
    for code, label, category in ACTION_TYPES:
        ActionType.objects.update_or_create(
            code=code,
            defaults={"label": label, "category": category},
        )


def backwards(apps, schema_editor):
    ActionType = apps.get_model("projects", "ActionType")
    ActionType.objects.filter(
        code__in=[c for c, _, _ in ACTION_TYPES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
```

Run: `uv run python manage.py migrate projects`
Expected: `Applying projects.0002_seed_actiontypes... OK`.

Verify: `uv run python manage.py shell -c "from projects.models import ActionType; print(ActionType.objects.count())"`
Expected: `5`.

- [ ] **Step 10: Run seed_superuser test**

Run: `uv run pytest tests/accounts/test_seed_superuser.py -v`
Expected: 2 passed.

- [ ] **Step 11: Commit**

```bash
git add accounts/migrations/0001_initial.py clients/migrations/0001_initial.py candidates/migrations/0001_initial.py projects/migrations/0001_initial.py projects/migrations/0002_seed_actiontypes.py data_extraction/migrations/0001_initial.py accounts/management/commands/seed_superuser.py accounts/management/__init__.py accounts/management/commands/__init__.py main/settings.py tests/accounts/test_seed_superuser.py
git add -u accounts/migrations/ clients/migrations/ candidates/migrations/ projects/migrations/ data_extraction/migrations/
git commit -m "$(cat <<'EOF'
chore(migrations): wipe + regenerate 0001_initial per app

Organization/Membership 제거 + organization FK 제거를 반영.
projects 에 ActionType seed data migration 추가.
accounts 에 seed_superuser 관리 커맨드.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 테스트 스위트 전면 개편

**목적:** 기존 Organization/Membership 기반 테스트 파일 삭제 또는 rewrite. conftest.py 정리.

**Files:**
- Delete: `tests/accounts/test_rbac.py`, `test_onboarding.py`, `test_org_management.py`, `test_invite_code.py`, `test_nav_org.py`
- Modify: `tests/conftest.py` (기존 `org`, `user`, `other_user`, `other_org_user`, `client_company`, `project`, `logged_in_client`, `other_org_client` fixture 제거 또는 level 기반 재작성)
- Modify: 남은 모든 tests/*.py 에서 `org`, `user`, `logged_in_client` 사용처를 level fixture 로 교체

- [ ] **Step 1: Delete obsolete test files**

Run:

```bash
rm tests/accounts/test_rbac.py
rm tests/accounts/test_onboarding.py
rm tests/accounts/test_org_management.py
rm tests/accounts/test_invite_code.py
rm tests/accounts/test_nav_org.py
```

- [ ] **Step 2: Rewrite conftest.py fully**

Overwrite `tests/conftest.py`:

```python
import pytest
from django.contrib.auth import get_user_model

from clients.models import Client
from projects.models import Project, ProjectStatus

User = get_user_model()


# --- Level-based user fixtures ---


@pytest.fixture
def pending_user(db):
    return User.objects.create_user(username="pending_u", password="x", level=0)


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff_u", password="x", level=1)


@pytest.fixture
def staff_user_2(db):
    return User.objects.create_user(username="staff_u2", password="x", level=1)


@pytest.fixture
def boss_user(db):
    return User.objects.create_user(username="boss_u", password="x", level=2)


@pytest.fixture
def dev_user(db):
    return User.objects.create_user(
        username="dev_u", password="x", level=2,
        is_superuser=True, is_staff=True,
    )


@pytest.fixture
def pending_client(client, pending_user):
    client.force_login(pending_user)
    return client


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def boss_client(client, boss_user):
    client.force_login(boss_user)
    return client


@pytest.fixture
def dev_client(client, dev_user):
    client.force_login(dev_user)
    return client


# --- Domain fixtures (no organization) ---


@pytest.fixture
def client_company(db):
    return Client.objects.create(name="Rayence")


@pytest.fixture
def project(db, client_company, boss_user):
    p = Project.objects.create(
        client=client_company,
        title="품질기획",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    return p


@pytest.fixture
def project_assigned_to_staff(db, client_company, staff_user):
    p = Project.objects.create(
        client=client_company,
        title="Assigned",
        status=ProjectStatus.OPEN,
        created_by=staff_user,
    )
    p.assigned_consultants.add(staff_user)
    return p


@pytest.fixture
def candidate(db):
    from candidates.models import Candidate
    return Candidate.objects.create(name="김후보")


@pytest.fixture
def application(db, project, candidate, boss_user):
    from projects.models import Application
    return Application.objects.create(
        project=project, candidate=candidate, created_by=boss_user
    )


@pytest.fixture
def second_application(db, project, boss_user):
    from candidates.models import Candidate
    from projects.models import Application
    c2 = Candidate.objects.create(name="이후보")
    return Application.objects.create(
        project=project, candidate=c2, created_by=boss_user
    )


@pytest.fixture
def third_candidate(db):
    from candidates.models import Candidate
    return Candidate.objects.create(name="박후보")


@pytest.fixture
def third_application(db, project, third_candidate, boss_user):
    from projects.models import Application
    return Application.objects.create(
        project=project, candidate=third_candidate, created_by=boss_user
    )


# --- ActionType fixtures (migration-seeded) ---


@pytest.fixture
def action_type_reach_out(db):
    from projects.models import ActionType
    return ActionType.objects.get(code="reach_out")


@pytest.fixture
def action_type_submit(db):
    from projects.models import ActionType
    return ActionType.objects.get(code="submit_to_client")


@pytest.fixture
def action_type_confirm_hire(db):
    from projects.models import ActionType
    return ActionType.objects.get(code="confirm_hire")


@pytest.fixture
def submission_factory(db, project, boss_user):
    from candidates.models import Candidate
    from projects.models import (
        ActionItem, ActionItemStatus, ActionType, Application, Submission,
    )

    counter = {"n": 0}

    def _make(**kwargs):
        batch_id = kwargs.pop("batch_id", None)
        counter["n"] += 1
        candidate = Candidate.objects.create(name=f"배치후보{counter['n']}")
        app = Application.objects.create(
            project=project, candidate=candidate, created_by=boss_user
        )
        at = ActionType.objects.get(code="submit_to_client")
        ai = ActionItem.objects.create(
            application=app, action_type=at, title="Test submit",
            status=ActionItemStatus.DONE,
        )
        return Submission.objects.create(action_item=ai, batch_id=batch_id)

    return _make


@pytest.fixture(autouse=True)
def _disable_manifest_storage(settings):
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


# --- Back-compat aliases for tests not yet fully rewritten ---


@pytest.fixture
def user(boss_user):
    """Back-compat: default logged-in user is now the boss."""
    return boss_user


@pytest.fixture
def other_user(staff_user_2):
    return staff_user_2


@pytest.fixture
def logged_in_client(boss_client):
    return boss_client
```

The back-compat aliases at the end let the remaining test files (test_views_dashboard.py, test_views.py, etc.) run unchanged as long as they only used `user`/`other_user`/`logged_in_client` without caring about organization.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest -x 2>&1 | tail -30`

Expected: mostly pass; failures flag tests that still reference `org` or `other_org_user`. Fix them inline by removing `org`/`other_org_user` params and the `Organization` import at each file's top.

- [ ] **Step 4: Delete remaining references to `other_org_user`**

Run: `uv run grep -rln "other_org_user\|other_org_client\|Organization.objects" tests/ 2>&1`

For each file, remove the fixture usage and the assertion "other org isolation". Since there are no other orgs anymore, these tests are obsolete — either delete them or convert them to "staff user cannot see other staff's projects" tests.

- [ ] **Step 5: Run full suite again**

Run: `uv run pytest 2>&1 | tail -10`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/
git add -u tests/accounts/test_rbac.py tests/accounts/test_onboarding.py tests/accounts/test_org_management.py tests/accounts/test_invite_code.py tests/accounts/test_nav_org.py
git commit -m "$(cat <<'EOF'
test: rewrite conftest around level-based fixtures; drop org tests

- pending_user/staff_user/boss_user/dev_user + matching clients
- back-compat aliases user/other_user/logged_in_client
- 기존 조직 isolation 테스트 삭제

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Phase 2a 대시보드 재연결

**목적:** `projects/services/dashboard.py` 시그니처를 `get_dashboard_context(user)` 로 단순화. `scope_owner = user.level >= 2 or user.is_superuser`. 뷰/테스트 갱신.

**Files:**
- Modify: `projects/services/dashboard.py` (시그니처 + scope_owner 계산 + 모든 helper)
- Modify: `projects/views.py:2141-2150` (dashboard 뷰)
- Modify: `tests/test_dashboard_phase2a.py` (fixture)

- [ ] **Step 1: Update failing dashboard test first**

Edit `tests/test_dashboard_phase2a.py`. Replace org/membership fixtures with level fixtures:

- Delete any top-level `org`, `owner`, `owner_client` fixtures defined in the test file (rely on conftest).
- Change `owner_client` → `boss_client`, `consultant_user` → `staff_user`.
- Drop `organization=org` kwargs from any `Project.objects.create(...)` / `Client.objects.create(...)`.
- Drop `Membership.objects.create(...)` calls (boss_user / staff_user already have correct level).
- For consultant scope test: ensure project has `assigned_consultants.add(staff_user)`.

Verify by running: `uv run pytest tests/test_dashboard_phase2a.py -v 2>&1 | tail -20`
Expected: failures because view still expects `request.user.membership`.

- [ ] **Step 2: Simplify dashboard service signature**

Edit `projects/services/dashboard.py`. Replace the public entry:

```python
def get_dashboard_context(user):
    scope_owner = user.is_superuser or user.level >= 2
    return {
        **_monthly_success(user, scope_owner),
        **_project_status_counts(user, scope_owner),
        **_team_performance(),
        **_weekly_schedule(user, scope_owner),
        **_monthly_calendar(user, scope_owner),
    }
```

Update all internal helpers to drop the `org` parameter and replace any `organization=org` filter with no filter (single-tenant):

Example — `_scope_projects`:

```python
def _scope_projects(user, scope_owner):
    qs = Project.objects.all()
    if scope_owner:
        return qs
    return qs.filter(assigned_consultants=user).distinct()
```

Apply similar stripping to `_monthly_success`, `_project_status_counts`, `_team_performance`, `_weekly_schedule`, `_monthly_calendar`.

`_team_performance`:

```python
def _team_performance():
    members = User.objects.filter(level__gte=1).order_by("-level", "date_joined")
    result = []
    for m in members:
        # ... existing aggregation logic, no org filter
        result.append(...)
    return {"team_performance": result}
```

Role label: `"대표"` when `m.level == 2`, `"컨설턴트"` when `m.level == 1`.

- [ ] **Step 3: Update dashboard view**

Edit `projects/views.py`. Find the `dashboard` view (~line 2141):

```python
@login_required
@level_required(1)
def dashboard(request):
    ctx = get_dashboard_context(request.user)
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", ctx)
    return render(request, "projects/dashboard.html", ctx)
```

- [ ] **Step 4: Run dashboard tests**

Run: `uv run pytest tests/test_dashboard_phase2a.py -v 2>&1 | tail -30`
Expected: 13 pass.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest 2>&1 | tail -10`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add projects/services/dashboard.py projects/views.py tests/test_dashboard_phase2a.py
git commit -m "$(cat <<'EOF'
refactor(dashboard): Phase 2a 를 Level 기반 권한 모델로 재연결

get_dashboard_context(user) 로 시그니처 단순화.
scope_owner = user.level >= 2 or user.is_superuser.
_team_performance 는 User.level >= 1 리스트 기반.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: deploy.sh --company 스텁 + 운영 DB 초기화 문서

**목적:** 현 단일 스택 그대로 두고, 미래 multi-company 확장을 위한 인자 파싱 자리만 확보. 운영 DB 초기화 절차를 `docs/deploy/company-reset.md` 에 기록.

**Files:**
- Modify: `deploy.sh` (아주 최상단에 `--company=SLUG` 파싱 추가, 지금은 `company="synco"` 로 고정)
- Create: `docs/deploy/company-reset.md`

- [ ] **Step 1: Add --company parsing stub to deploy.sh**

Edit `deploy.sh`. Near the top, add:

```bash
# --company=SLUG 인자 파싱 (현재는 single-tenant, 값 무시하고 "synco" 고정).
# 2번째 회사가 추가될 때 이 스텁을 실구현.
company="synco"
for arg in "$@"; do
    case "$arg" in
        --company=*) company="${arg#*=}" ;;
    esac
done
export SYNCO_COMPANY_SLUG="$company"
echo ">>> Deploying synco (company=$company)"
```

- [ ] **Step 2: Write company-reset doc**

Create `docs/deploy/company-reset.md`:

```markdown
# 운영 DB 초기화 + 슈퍼유저 시드

Single-tenant 리팩터 이후 최초 배포 시 1회 실행.

## 사전 조건

- 코드가 `main` 기준이며 Organization/Membership 이 제거되고 새 `0001_initial.py` 마이그레이션만 남아 있어야 한다.
- `.env.prod` 에 `SYNCO_SUPERUSER_EMAIL=chaconne67@gmail.com` 존재.

## 절차

1. 운영 DB 백업 (선택):
   ```bash
   ssh chaconne@49.247.45.243 \
     "docker exec synco-pg pg_dump -U synco synco > /tmp/synco-preresfresh.sql"
   ```

2. 운영 DB drop + recreate:
   ```bash
   ssh chaconne@49.247.45.243 \
     "docker exec synco-pg psql -U postgres -c 'DROP DATABASE synco;'"
   ssh chaconne@49.247.45.243 \
     "docker exec synco-pg psql -U postgres -c 'CREATE DATABASE synco OWNER synco;'"
   ```

3. 배포 (deploy.sh 가 마이그레이션 자동 실행):
   ```bash
   ./deploy.sh
   ```

4. Superuser 시드:
   ```bash
   ssh chaconne@49.247.46.171 \
     "docker exec \$(docker ps -qf name=synco_web) python manage.py seed_superuser"
   ```

5. 확인:
   - chaconne67@gmail.com 으로 카카오 로그인 → 대시보드 진입
   - `/admin` 접근 가능 (is_superuser=True)

## 차후: 두 번째 회사 배포

`deploy.sh --company=B` 구현 시점에 본 문서를 회사별 절차로 확장.
```

- [ ] **Step 3: Commit**

```bash
git add deploy.sh docs/deploy/company-reset.md
git commit -m "$(cat <<'EOF'
chore(deploy): --company=SLUG 스텁 + 운영 DB 초기화 절차 문서화

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: 운영 배포 (사용자 명시 승인 필수)

**목적:** 운영 서버에 반영. 이 태스크는 **사용자가 명시적으로 "배포해"** 라고 승인한 뒤에만 실행. 기본 어시스턴트는 실행하지 말고 절차만 준비.

**Preconditions:**
- T1~T11 전부 merged on `main`.
- `./deploy.sh` 로컬 smoke 스크립트로 이미지 빌드 성공.
- 사용자가 명시적으로 "배포해" 또는 동등한 승인 발화.

- [ ] **Step 1: 사용자 명시 승인 확인**

Assistant 는 이 태스크 실행 전 **반드시** 사용자에게 다음을 확인:

- "T1~T11 까지 main 에 머지되었습니다. 운영 DB (49.247.45.243) 를 drop & recreate 하고 재배포합니다. 진행할까요?"

- [ ] **Step 2: 운영 DB 백업 (선택 but 권장)**

```bash
ssh chaconne@49.247.45.243 \
  "docker exec synco-pg pg_dump -U synco synco > /tmp/synco-prerefresh-$(date +%Y%m%d-%H%M).sql"
```

- [ ] **Step 3: 운영 DB 초기화**

```bash
ssh chaconne@49.247.45.243 \
  "docker exec synco-pg psql -U postgres -c 'DROP DATABASE synco;'"
ssh chaconne@49.247.45.243 \
  "docker exec synco-pg psql -U postgres -c 'CREATE DATABASE synco OWNER synco;'"
```

- [ ] **Step 4: 배포 실행**

```bash
./deploy.sh
```

Expected: 이미지 빌드 → push → swarm update → 마이그레이션 자동 실행.

- [ ] **Step 5: 슈퍼유저 시드**

```bash
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py seed_superuser"
```

Expected 출력: `Superuser ensured: chaconne67@gmail.com (level=2, is_superuser=True)`.

- [ ] **Step 6: 스모크 테스트**

- `https://<운영 도메인>/accounts/kakao/login/` 으로 카카오 로그인
- 대시보드 렌더 확인
- `/admin` 접근 가능한지 확인
- 신규 테스트 유저 (kakao 로그인 신규 계정) 가 대기 페이지로 리다이렉트되는지 확인
- 해당 신규 유저를 `/admin` 에서 `level=1` 로 승급 → 대시보드 진입 확인

- [ ] **Step 7: 완료 보고**

배포 완료 후 사용자에게 보고:
- 배포된 커밋 SHA
- 슈퍼유저 시드 출력
- 스모크 결과

배포 자체 커밋은 없음 (`main` 그대로).

---

## Self-Review Summary

1. **Spec 커버리지:**
   - 회사별 완전 독립 배포 → T11/T12
   - Organization/Membership 제거 → T6
   - organization FK 제거 → T7
   - `User.level` 필드 추가 → T1
   - `level_required` / `superuser_required` 데코레이터 → T2
   - `scope_work_qs` 헬퍼 → T2
   - 카카오 단일 로그인 → T3
   - 승인 대기 페이지 (버튼 disable 분기) → T3
   - django-hijack → T4
   - 마이그레이션 wipe + 재생성 → T8
   - seed_superuser 커맨드 → T8
   - ActionType 시드 → T8
   - 테스트 스위트 전면 개편 → T9
   - Phase 2a 대시보드 재연결 → T10
   - deploy.sh --company 스텁 → T11
   - 운영 배포 → T12

2. **Placeholder scan:** 모든 "TBD"/"나중에"/"적절히 처리" 제거 완료. 코드 블록은 실제 사용 가능한 형태로 작성.

3. **타입 일관성:** `User.level` (IntegerField) · `User.is_superuser` (bool) · `scope_work_qs(qs, user, assigned_field="assigned_consultants")` · `get_dashboard_context(user)` · 모든 fixture 이름 (`pending_user`, `staff_user`, `boss_user`, `dev_user` + 각 `_client` 변형) 모든 Task 에 걸쳐 일관되게 사용.

4. **기억된 제약 반영:**
   - 더미 데이터 보존 (T7/T8 에서 dev DB 는 reset 하지만 dummy data 는 scope 밖 이슈 — 운영에서는 migration 재실행으로 기존 더미가 wipe 되므로 실제 더미 보존은 어차피 불가능. 대신 T8 은 애초에 더미가 "없는" 상태에서 진행됨을 전제).
   - 배포는 사용자 명시 승인 필요 → T12 Step 1 에 명시.
   - 개발 서버는 사용자가 실행 (T8 Step 6 `docker compose up -d` 는 DB 만 포함. runserver 는 사용자가 직접).
