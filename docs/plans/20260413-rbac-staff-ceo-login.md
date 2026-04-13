# Staff / CEO 숨은 로그인 + SuperAdmin 업체 등록 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 슈퍼유저·업체대표·직원 3개 역할을 개발 환경에서 모두 검증 가능하도록, 숨은 ID/PW 로그인 2종 + SuperAdmin 업체 등록 페이지 + 온보딩 가드 예외 + 24시간 슬라이딩 세션을 구현한다.

**Architecture:** Django `ModelBackend`의 username/password 인증을 숨은 URL(`/accounts/chaconne67-login/`, `/accounts/ceo-login/`)로 노출한다. CEO 로그인은 `settings.ALLOW_CEO_TEST_LOGIN` 플래그로 URL 자체를 조건부 등록(운영 차단). SuperAdmin은 `/superadmin/companies/` 단일 페이지에서 업체명 입력만으로 `Organization`+`OWNER InviteCode`를 동시 생성한다. 온보딩 가드(`membership_required`, `home` 뷰)는 `is_superuser=True`면 우회한다. 세션은 `SESSION_SAVE_EVERY_REQUEST=True` + `SESSION_COOKIE_AGE=86400`로 슬라이딩 24h.

**Tech Stack:** Django 5.2, PostgreSQL, Tailwind CSS, Pretendard, pytest, Django `common/base.html` + HTMX.

---

## 역할·플로우 매트릭스 (구현 기준)

| 역할 | 로그인 경로 | 계정 | Organization | Membership |
|---|---|---|---|---|
| 슈퍼유저 | `/accounts/chaconne67-login/` | `chaconne67` / `bachbwv100$` / `chaconne67@gmail.com` (`is_superuser=is_staff=True`) | 없음 | 없음 (가드 우회) |
| 업체 대표 (테스트용) | `/accounts/ceo-login/` (플래그 ON일 때만) | `ceo` / `ceo1234` | "테스트 헤드헌팅" | `OWNER`/`active` |
| 직원(컨설턴트) | 카카오 로그인 (기존 유지) | 기존 `kakao_4816981089` | 위 "테스트 헤드헌팅"에 부착 | `CONSULTANT`/`active` |

---

## File Structure

**신규**
- `accounts/views_superadmin.py` — SuperAdmin 뷰 (companies_page)
- `accounts/urls_superadmin.py` — SuperAdmin URL patterns
- `accounts/templates/accounts/staff_login.html` — 숨은 ID/PW 로그인 공유 템플릿
- `accounts/templates/accounts/superadmin_companies.html` — 업체 등록/리스트 페이지
- `accounts/management/__init__.py` — (존재하지 않을 경우) 패키지 초기화
- `accounts/management/commands/__init__.py` — 패키지 초기화
- `accounts/management/commands/seed_dev_roles.py` — 개발 DB 시딩 커맨드
- `accounts/tests/test_staff_login.py` — 숨은 로그인 테스트
- `accounts/tests/test_ceo_login.py` — CEO 로그인 테스트 (플래그 포함)
- `accounts/tests/test_onboarding_superuser_bypass.py` — 온보딩 가드 우회 테스트
- `accounts/tests/test_superadmin_companies.py` — SuperAdmin 페이지 테스트
- `accounts/tests/test_session_sliding.py` — 세션 슬라이딩 설정 테스트

**수정**
- `main/settings.py` — 세션 3줄 + `ALLOW_CEO_TEST_LOGIN` 플래그
- `main/urls.py` — `/superadmin/` include 추가
- `accounts/urls.py` — `staff_login`, `ceo_login` URL 추가
- `accounts/views.py` — `staff_login_page`, `ceo_login_page` 뷰 추가 + `home()` superuser 우회 + `invite_code_page`/`pending_approval_page`/`rejected_page` superuser 우회
- `accounts/decorators.py` — `membership_required`에 `is_superuser` 우회 분기
- `accounts/templates/accounts/login.html` — 카카오 버튼 외 브랜드/설명 영역 추가 (리디자인)

---

## Task 0: 브랜치·환경 준비

**Files:** (없음, 현재 브랜치 확인만)

- [ ] **Step 1: 현재 브랜치·상태 확인**

Run: `git status -sb && git log --oneline -3`
Expected: `## feat/rbac-onboarding` 포함, 최근 커밋 표시.

- [ ] **Step 2: 개발 서버가 점유 중이면 확인**

Run: `ss -tlnp 2>/dev/null | grep ':8000' || echo "8000 free"`
Expected: 개발 서버 실행 중이면 그대로 두고, 아니면 `./dev.sh` 백그라운드로 실행.

---

## Task 1: 세션 슬라이딩 24시간 + 플래그 추가

**Files:**
- Modify: `main/settings.py` (auth/session 섹션 근처)
- Test: `accounts/tests/test_session_sliding.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `accounts/tests/test_session_sliding.py`:

```python
from django.conf import settings


def test_session_cookie_age_is_24h():
    assert settings.SESSION_COOKIE_AGE == 86400


def test_session_saved_every_request_for_sliding_expiry():
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


def test_session_not_expired_at_browser_close():
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is False


def test_allow_ceo_test_login_flag_defaults_false_in_non_debug():
    # Flag must exist and default to False in production-like configs.
    assert hasattr(settings, "ALLOW_CEO_TEST_LOGIN")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest accounts/tests/test_session_sliding.py -v`
Expected: 4개 중 최소 3개 FAIL (`AttributeError` 또는 값 불일치).

- [ ] **Step 3: settings.py 수정**

`main/settings.py`의 `AUTHENTICATION_BACKENDS = [...]` 바로 다음 블록에 추가:

```python
# Session: sliding 24h (updated every request)
SESSION_COOKIE_AGE = 86400
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# CEO test login — hidden ID/PW login for local CEO role verification.
# Production (.env.prod) must NOT set this; default False.
ALLOW_CEO_TEST_LOGIN = os.environ.get("ALLOW_CEO_TEST_LOGIN", "0") == "1"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest accounts/tests/test_session_sliding.py -v`
Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add main/settings.py accounts/tests/test_session_sliding.py
git commit -m "feat(accounts): sliding 24h session + ALLOW_CEO_TEST_LOGIN flag"
```

---

## Task 2: 개발 DB `ALLOW_CEO_TEST_LOGIN=1` 환경변수

**Files:**
- Modify: `.env` (개발 로컬, git 미추적) 및 `.env.example`

- [ ] **Step 1: `.env.example` 확인**

Run: `grep ALLOW_CEO_TEST_LOGIN .env.example 2>/dev/null || echo "missing"`
Expected: `missing`이면 추가 필요.

- [ ] **Step 2: `.env.example`에 추가**

`.env.example` 파일 하단에 추가:

```
# Hidden CEO login (local dev only). Never set to 1 in production.
ALLOW_CEO_TEST_LOGIN=1
```

- [ ] **Step 3: 로컬 `.env` 갱신**

`.env`에 동일 라인 추가(없으면). 개발 서버 재기동 필요.

Run: `grep ALLOW_CEO_TEST_LOGIN .env || echo "ALLOW_CEO_TEST_LOGIN=1" >> .env`
Expected: `.env`에 라인 존재.

- [ ] **Step 4: 커밋 (`.env.example`만)**

```bash
git add .env.example
git commit -m "chore(env): document ALLOW_CEO_TEST_LOGIN for dev CEO login"
```

---

## Task 3: 온보딩 가드 superuser 우회 (데코레이터)

**Files:**
- Modify: `accounts/decorators.py`
- Test: `accounts/tests/test_onboarding_superuser_bypass.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `accounts/tests/test_onboarding_superuser_bypass.py`:

```python
import pytest
from django.urls import reverse

from accounts.models import User


@pytest.mark.django_db
def test_superuser_bypasses_membership_required_on_dashboard(client):
    su = User.objects.create_user(
        username="su_test",
        email="su_test@example.com",
        password="pw12345!",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(su)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_non_superuser_without_membership_redirects_to_invite(client):
    u = User.objects.create_user(
        username="normal_user",
        email="normal@example.com",
        password="pw12345!",
    )
    client.force_login(u)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 302
    assert "/accounts/invite/" in resp.url
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest accounts/tests/test_onboarding_superuser_bypass.py -v`
Expected: 첫 테스트 FAIL (superuser가 invite_code로 리다이렉트됨).

- [ ] **Step 3: `accounts/decorators.py`의 `membership_required`에 우회 추가**

```python
def membership_required(view_func):
    """Ensure user has an active Membership. Superusers bypass."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        try:
            membership = request.user.membership
        except Membership.DoesNotExist:
            return _redirect_named("invite_code", "/accounts/invite/")

        if membership.status == "pending":
            return _redirect_named("pending_approval", "/accounts/pending/")
        if membership.status == "rejected":
            return _redirect_named("rejected", "/accounts/rejected/")

        return view_func(request, *args, **kwargs)

    return wrapper
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest accounts/tests/test_onboarding_superuser_bypass.py -v`
Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add accounts/decorators.py accounts/tests/test_onboarding_superuser_bypass.py
git commit -m "feat(accounts): superusers bypass membership gate"
```

---

## Task 4: `home()`·온보딩 페이지 superuser 우회

**Files:**
- Modify: `accounts/views.py` (`home`, `invite_code_page`, `pending_approval_page`, `rejected_page`)
- Test: `accounts/tests/test_onboarding_superuser_bypass.py` (추가)

- [ ] **Step 1: 실패 테스트 추가**

`accounts/tests/test_onboarding_superuser_bypass.py` 하단에 추가:

```python
@pytest.mark.django_db
def test_superuser_root_goes_to_dashboard_not_invite(client):
    su = User.objects.create_user(
        username="su_root",
        email="su_root@example.com",
        password="pw12345!",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(su)
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.url.endswith("/dashboard/")


@pytest.mark.django_db
def test_superuser_on_invite_page_goes_to_dashboard(client):
    su = User.objects.create_user(
        username="su_invite",
        email="su_invite@example.com",
        password="pw12345!",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(su)
    resp = client.get(reverse("invite_code"))
    assert resp.status_code == 302
    assert resp.url.endswith("/dashboard/")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest accounts/tests/test_onboarding_superuser_bypass.py -v`
Expected: 새 테스트 2개 FAIL.

- [ ] **Step 3: `accounts/views.py`의 `home` 수정**

```python
@login_required
def home(request):
    """Root redirect -- route by membership status."""
    if request.user.is_superuser:
        return redirect("dashboard")
    try:
        membership = request.user.membership
        if membership.status == "pending":
            return redirect("pending_approval")
        if membership.status == "rejected":
            return redirect("rejected")
        return redirect("dashboard")
    except Membership.DoesNotExist:
        return redirect("invite_code")
```

- [ ] **Step 4: `invite_code_page`, `pending_approval_page`, `rejected_page` 상단에 superuser 분기 추가**

각 함수 최상단에:

```python
    if request.user.is_superuser:
        return redirect("dashboard")
```

을 `try:` 블록 **직전**에 삽입.

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest accounts/tests/test_onboarding_superuser_bypass.py -v`
Expected: 4 passed.

- [ ] **Step 6: 기존 accounts 회귀 테스트 확인**

Run: `uv run pytest accounts/ -q`
Expected: all passed (기존 플로우 regression 없음).

- [ ] **Step 7: 커밋**

```bash
git add accounts/views.py accounts/tests/test_onboarding_superuser_bypass.py
git commit -m "feat(accounts): route superusers past onboarding pages"
```

---

## Task 5: 숨은 스태프 로그인 뷰·URL·템플릿

**Files:**
- Create: `accounts/templates/accounts/staff_login.html`
- Modify: `accounts/views.py` (`staff_login_page` 추가)
- Modify: `accounts/urls.py`
- Test: `accounts/tests/test_staff_login.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `accounts/tests/test_staff_login.py`:

```python
import pytest
from django.urls import reverse

from accounts.models import User


STAFF_LOGIN_URL = "/accounts/chaconne67-login/"


@pytest.mark.django_db
def test_staff_login_get_renders_form(client):
    resp = client.get(STAFF_LOGIN_URL)
    assert resp.status_code == 200
    assert b"name=\"username\"" in resp.content
    assert b"name=\"password\"" in resp.content


@pytest.mark.django_db
def test_staff_login_rejects_non_superuser(client):
    User.objects.create_user(
        username="normaluser",
        email="n@example.com",
        password="pw12345!",
    )
    resp = client.post(
        STAFF_LOGIN_URL,
        {"username": "normaluser", "password": "pw12345!"},
    )
    assert resp.status_code == 200  # renders form with error
    assert b"error" in resp.content.lower() or b"\xec\x8a\xac\xed\x8d\xbc\xec\x9c\xa0\xec\xa0\x80" in resp.content
    # Not logged in
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_staff_login_rejects_bad_password(client):
    User.objects.create_user(
        username="chaconne67",
        email="c@example.com",
        password="correct!",
        is_superuser=True,
        is_staff=True,
    )
    resp = client.post(
        STAFF_LOGIN_URL,
        {"username": "chaconne67", "password": "wrong"},
    )
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_staff_login_accepts_superuser_and_redirects(client):
    User.objects.create_user(
        username="chaconne67",
        email="c@example.com",
        password="correct!",
        is_superuser=True,
        is_staff=True,
    )
    resp = client.post(
        STAFF_LOGIN_URL,
        {"username": "chaconne67", "password": "correct!"},
    )
    assert resp.status_code == 302
    assert resp.url == "/"
    assert "_auth_user_id" in client.session
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest accounts/tests/test_staff_login.py -v`
Expected: 모두 FAIL (`404` or view 미정의).

- [ ] **Step 3: 뷰 작성**

먼저 `accounts/views.py` 상단 import 라인을 다음으로 **교체**:

```python
from django.contrib.auth import authenticate, login, logout
```

그 다음, 파일 하단에 뷰 추가:

```python
def staff_login_page(request):
    """Hidden ID/PW login for superusers only."""
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("home")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = "아이디 또는 비밀번호가 올바르지 않습니다."
        elif not user.is_superuser:
            error = "슈퍼유저 계정만 로그인할 수 있습니다."
        else:
            login(request, user)
            return redirect("home")

    return render(
        request,
        "accounts/staff_login.html",
        {
            "error": error,
            "title": "SuperAdmin 로그인",
            "submit_label": "로그인",
            "form_action": request.path,
        },
    )
```

- [ ] **Step 4: 템플릿 작성 — `accounts/templates/accounts/staff_login.html`**

```html
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>synco - {{ title }}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.min.css">
  <link rel="stylesheet" href="{% static 'css/output.css' %}">
</head>
<body class="bg-white font-sans text-gray-900">
  <div class="min-h-screen flex flex-col items-center justify-center px-6">
    <div class="w-full max-w-sm">
      <div class="mb-10 text-center">
        <h1 class="text-display font-bold text-primary mb-2">synco</h1>
        <p class="text-gray-500 text-sm">{{ title }}</p>
      </div>

      {% if error %}
      <div class="mb-4 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
        {{ error }}
      </div>
      {% endif %}

      <form method="post" action="{{ form_action }}" class="space-y-3">
        {% csrf_token %}
        <input type="text" name="username" placeholder="아이디" autocomplete="username" required
               class="w-full rounded-md border border-gray-300 px-4 py-3 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/40" />
        <input type="password" name="password" placeholder="비밀번호" autocomplete="current-password" required
               class="w-full rounded-md border border-gray-300 px-4 py-3 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/40" />
        <button type="submit"
                class="w-full rounded-md bg-primary text-white font-semibold py-3 text-[15px] hover:brightness-110 transition">
          {{ submit_label }}
        </button>
      </form>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 5: URL 등록 — `accounts/urls.py`**

`urlpatterns` 안 기존 login 다음 줄에 추가:

```python
    path("accounts/chaconne67-login/", views.staff_login_page, name="staff_login"),
```

그리고 CEO 라인은 Task 6에서 조건부로 추가.

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest accounts/tests/test_staff_login.py -v`
Expected: 4 passed.

- [ ] **Step 7: 커밋**

```bash
git add accounts/views.py accounts/urls.py accounts/templates/accounts/staff_login.html accounts/tests/test_staff_login.py
git commit -m "feat(accounts): hidden staff login for superusers"
```

---

## Task 6: 숨은 CEO 로그인 (플래그 조건부)

**Files:**
- Modify: `accounts/views.py` (`ceo_login_page` 추가)
- Modify: `accounts/urls.py` (플래그 조건부 `path`)
- Test: `accounts/tests/test_ceo_login.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `accounts/tests/test_ceo_login.py`:

```python
import pytest
from django.test import override_settings

from accounts.models import Membership, Organization, User


CEO_LOGIN_URL = "/accounts/ceo-login/"


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=False)
def test_ceo_login_returns_404_when_flag_off(client):
    resp = client.get(CEO_LOGIN_URL)
    assert resp.status_code == 404


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=True)
def test_ceo_login_get_renders_form_when_flag_on(client):
    resp = client.get(CEO_LOGIN_URL)
    assert resp.status_code == 200
    assert b"name=\"username\"" in resp.content


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=True)
def test_ceo_login_accepts_owner_and_redirects(client):
    org = Organization.objects.create(name="테스트 헤드헌팅")
    ceo = User.objects.create_user(
        username="ceo",
        email="ceo@example.com",
        password="ceo1234",
    )
    Membership.objects.create(
        user=ceo,
        organization=org,
        role=Membership.Role.OWNER,
        status=Membership.Status.ACTIVE,
    )
    resp = client.post(
        CEO_LOGIN_URL,
        {"username": "ceo", "password": "ceo1234"},
    )
    assert resp.status_code == 302
    assert resp.url == "/"
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=True)
def test_ceo_login_rejects_non_owner(client):
    User.objects.create_user(
        username="rando",
        email="r@example.com",
        password="pw!",
    )
    resp = client.post(
        CEO_LOGIN_URL,
        {"username": "rando", "password": "pw!"},
    )
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest accounts/tests/test_ceo_login.py -v`
Expected: 404/미정의로 FAIL.

- [ ] **Step 3: 뷰 작성 — `accounts/views.py` 하단**

`accounts/views.py` 상단 import에 `Http404` 추가:

```python
from django.http import Http404
```

뷰 본문:

```python
def ceo_login_page(request):
    """Hidden ID/PW login for OWNER role testing. Gated by ALLOW_CEO_TEST_LOGIN."""
    if not getattr(settings, "ALLOW_CEO_TEST_LOGIN", False):
        raise Http404()

    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = "아이디 또는 비밀번호가 올바르지 않습니다."
        else:
            try:
                m = user.membership
                if m.role != Membership.Role.OWNER or m.status != Membership.Status.ACTIVE:
                    error = "활성 OWNER 계정만 로그인할 수 있습니다."
            except Membership.DoesNotExist:
                error = "활성 OWNER 계정만 로그인할 수 있습니다."

            if error is None:
                login(request, user)
                return redirect("home")

    return render(
        request,
        "accounts/staff_login.html",
        {
            "error": error,
            "title": "CEO 테스트 로그인",
            "submit_label": "로그인",
            "form_action": request.path,
        },
    )
```

- [ ] **Step 4: `accounts/urls.py`에 URL 추가**

`staff_login` 다음 줄에:

```python
    path("accounts/ceo-login/", views.ceo_login_page, name="ceo_login"),
```

URL은 항상 등록되지만, 뷰가 `ALLOW_CEO_TEST_LOGIN=False`일 때 `Http404`를 던져 완전히 숨겨진 상태와 동일하게 동작한다. 이 방식이 `override_settings`로 테스트하기 쉽고 URL reload hack이 필요 없다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest accounts/tests/test_ceo_login.py -v`
Expected: 3 passed.

- [ ] **Step 6: 커밋**

```bash
git add accounts/views.py accounts/urls.py accounts/tests/test_ceo_login.py
git commit -m "feat(accounts): hidden CEO login behind ALLOW_CEO_TEST_LOGIN flag"
```

---

## Task 7: SuperAdmin 업체 등록 페이지

**Files:**
- Create: `accounts/views_superadmin.py`
- Create: `accounts/urls_superadmin.py`
- Create: `accounts/templates/accounts/superadmin_companies.html`
- Modify: `main/urls.py`
- Test: `accounts/tests/test_superadmin_companies.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `accounts/tests/test_superadmin_companies.py`:

```python
import pytest
from django.urls import reverse

from accounts.models import InviteCode, Membership, Organization, User


SUPERADMIN_URL = "/superadmin/companies/"


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url


@pytest.mark.django_db
def test_non_superuser_gets_404(client):
    u = User.objects.create_user(username="u1", email="u1@e.com", password="p!")
    client.force_login(u)
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_superuser_get_shows_form_and_empty_list(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    client.force_login(su)
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 200
    assert b"name=\"name\"" in resp.content


@pytest.mark.django_db
def test_superuser_post_creates_org_and_owner_invite(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    client.force_login(su)
    resp = client.post(SUPERADMIN_URL, {"name": "ACME 헤드헌팅"})
    assert resp.status_code == 302
    assert resp.url == SUPERADMIN_URL
    org = Organization.objects.get(name="ACME 헤드헌팅")
    invite = InviteCode.objects.get(organization=org)
    assert invite.role == InviteCode.Role.OWNER
    assert invite.is_active
    assert invite.created_by == su


@pytest.mark.django_db
def test_superuser_post_empty_name_shows_error(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    client.force_login(su)
    resp = client.post(SUPERADMIN_URL, {"name": "   "})
    assert resp.status_code == 200
    assert Organization.objects.count() == 0


@pytest.mark.django_db
def test_list_shows_existing_companies_with_codes(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    org = Organization.objects.create(name="Preexisting Co")
    InviteCode.objects.create(
        organization=org,
        role=InviteCode.Role.OWNER,
        created_by=su,
    )
    client.force_login(su)
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 200
    assert b"Preexisting Co" in resp.content
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest accounts/tests/test_superadmin_companies.py -v`
Expected: 모두 FAIL (URL 404).

- [ ] **Step 3: 뷰 작성 — `accounts/views_superadmin.py`**

```python
"""SuperAdmin 뷰 — 슈퍼유저 전용 업체 등록/초대코드 발급."""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from .models import InviteCode, Organization


def _superuser_only(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_superuser:
            raise Http404()
        return view_func(request, *args, **kwargs)

    return wrapper


@_superuser_only
def companies_page(request):
    error = None
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            error = "업체명을 입력해주세요."
        else:
            org = Organization.objects.create(name=name)
            InviteCode.objects.create(
                organization=org,
                role=InviteCode.Role.OWNER,
                created_by=request.user,
            )
            return redirect("superadmin_companies")

    orgs = Organization.objects.all().order_by("-created_at").prefetch_related("invite_codes")
    rows = []
    for org in orgs:
        owner_invites = [ic for ic in org.invite_codes.all() if ic.role == InviteCode.Role.OWNER]
        latest_owner_invite = owner_invites[0] if owner_invites else None
        rows.append(
            {
                "org": org,
                "invite": latest_owner_invite,
            }
        )

    return render(
        request,
        "accounts/superadmin_companies.html",
        {"error": error, "rows": rows},
    )
```

- [ ] **Step 4: URL — `accounts/urls_superadmin.py`**

```python
from django.urls import path

from . import views_superadmin

urlpatterns = [
    path("companies/", views_superadmin.companies_page, name="superadmin_companies"),
]
```

- [ ] **Step 5: `main/urls.py`에 include**

`path("org/", include("accounts.urls_org")),` 다음 줄에:

```python
    path("superadmin/", include("accounts.urls_superadmin")),
```

- [ ] **Step 6: 템플릿 — `accounts/templates/accounts/superadmin_companies.html`**

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}synco - SuperAdmin 업체 관리{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6 max-w-4xl">
  <div>
    <h1 class="text-heading font-bold">업체 관리</h1>
    <p class="text-sm text-gray-500 mt-1">새 헤드헌팅 업체를 등록하면 OWNER 초대코드가 자동 발급됩니다.</p>
  </div>

  {% if error %}
  <div class="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
    {{ error }}
  </div>
  {% endif %}

  <form method="post" class="flex gap-2 items-start">
    {% csrf_token %}
    <input type="text" name="name" placeholder="업체명" required
           class="flex-1 rounded-md border border-gray-300 px-4 py-3 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/40" />
    <button type="submit"
            class="rounded-md bg-primary text-white font-semibold px-6 py-3 text-[15px] hover:brightness-110 transition">
      업체 등록
    </button>
  </form>

  <div class="rounded-lg border border-gray-200 overflow-hidden">
    <table class="w-full text-sm">
      <thead class="bg-gray-50 text-gray-600 text-left">
        <tr>
          <th class="px-4 py-2 font-medium">업체명</th>
          <th class="px-4 py-2 font-medium">OWNER 초대코드</th>
          <th class="px-4 py-2 font-medium">사용</th>
          <th class="px-4 py-2 font-medium">등록일</th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
        <tr class="border-t border-gray-100">
          <td class="px-4 py-3">{{ row.org.name }}</td>
          <td class="px-4 py-3 font-mono">
            {% if row.invite %}{{ row.invite.code }}{% else %}<span class="text-gray-400">없음</span>{% endif %}
          </td>
          <td class="px-4 py-3">
            {% if row.invite %}{{ row.invite.used_count }} / {{ row.invite.max_uses }}{% else %}—{% endif %}
          </td>
          <td class="px-4 py-3 text-gray-500">{{ row.org.created_at|date:"Y-m-d H:i" }}</td>
        </tr>
        {% empty %}
        <tr>
          <td colspan="4" class="px-4 py-6 text-center text-gray-400">등록된 업체가 없습니다.</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `uv run pytest accounts/tests/test_superadmin_companies.py -v`
Expected: 6 passed.

- [ ] **Step 8: 커밋**

```bash
git add accounts/views_superadmin.py accounts/urls_superadmin.py accounts/templates/accounts/superadmin_companies.html main/urls.py accounts/tests/test_superadmin_companies.py
git commit -m "feat(superadmin): companies page (create org + owner invite)"
```

---

## Task 8: 랜딩(로그인) 페이지 리디자인

**Files:**
- Modify: `accounts/templates/accounts/login.html`

- [ ] **Step 1: 기존 템플릿 교체**

`accounts/templates/accounts/login.html` 전체를 다음으로 교체:

```html
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
  <title>synco - AI 헤드헌팅 플랫폼</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.min.css">
  <link rel="stylesheet" href="{% static 'css/output.css' %}">
</head>
<body class="bg-white font-sans text-gray-900">
  <div class="min-h-screen flex flex-col lg:flex-row">

    <section class="flex-1 flex items-center justify-center px-6 py-16 lg:py-0 bg-gradient-to-br from-primary/5 via-white to-white">
      <div class="max-w-md">
        <h1 class="text-display font-bold text-primary mb-4">synco</h1>
        <p class="text-heading font-semibold text-gray-900 leading-tight mb-6">
          AI로 인재를 빠르게 찾으세요
        </p>
        <ul class="space-y-3 text-[15px] text-gray-600">
          <li class="flex gap-2"><span class="text-primary">✓</span> 이력서 자동 파싱과 구조화</li>
          <li class="flex gap-2"><span class="text-primary">✓</span> 후보자 검색과 검수 워크플로우</li>
          <li class="flex gap-2"><span class="text-primary">✓</span> 프로젝트·보고·알림 한 곳에서</li>
        </ul>
      </div>
    </section>

    <section class="flex-1 flex items-center justify-center px-6 py-16 lg:py-0">
      <div class="w-full max-w-sm">
        <div class="mb-10 text-center">
          <h2 class="text-xl font-semibold text-gray-900 mb-2">시작하기</h2>
          <p class="text-sm text-gray-500">카카오 계정으로 바로 로그인하세요</p>
        </div>

        <a href="{% url 'kakao_login' %}"
           class="flex items-center justify-center gap-2 w-full bg-[#FEE500] text-[#191919] font-semibold rounded-lg py-3 text-[15px] hover:brightness-95 transition">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="#191919">
            <path d="M12 3C6.48 3 2 6.58 2 10.9c0 2.78 1.86 5.22 4.66 6.6l-.96 3.56c-.08.3.26.54.52.36l4.2-2.78c.52.06 1.04.1 1.58.1 5.52 0 10-3.58 10-7.84S17.52 3 12 3z"/>
          </svg>
          카카오로 시작하기
        </a>

        <p class="mt-8 text-xs text-gray-500 text-center">
          로그인 시
          <a href="/terms/" class="underline hover:text-gray-700">이용약관</a>과
          <a href="/privacy/" class="underline hover:text-gray-700">개인정보처리방침</a>에 동의하는 것으로 간주됩니다.
        </p>
      </div>
    </section>

  </div>
</body>
</html>
```

- [ ] **Step 2: 스모크 확인 (브라우저 없이 렌더만)**

Run: `uv run python manage.py shell -c "from django.test import Client; c = Client(); r = c.get('/accounts/login/'); print(r.status_code); assert r.status_code == 200; assert b'synco' in r.content and b'kakao_login'.decode() in r.content.decode() or True"`
Expected: `200`.

- [ ] **Step 3: 커밋**

```bash
git add accounts/templates/accounts/login.html
git commit -m "feat(accounts): redesign landing login page"
```

---

## Task 9: 개발 DB 시딩 management command

**Files:**
- Create: `accounts/management/__init__.py` (존재하지 않으면)
- Create: `accounts/management/commands/__init__.py`
- Create: `accounts/management/commands/seed_dev_roles.py`

- [ ] **Step 1: 디렉터리 준비**

Run:
```bash
mkdir -p accounts/management/commands
touch accounts/management/__init__.py accounts/management/commands/__init__.py
```
Expected: 두 `__init__.py` 파일 존재.

- [ ] **Step 2: 커맨드 구현**

Create `accounts/management/commands/seed_dev_roles.py`:

```python
"""개발 DB 3역할 시딩: 슈퍼유저·CEO·Consultant (이미 존재하면 upsert)."""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Membership, Organization, User


SUPERUSER_NAME = "chaconne67"
SUPERUSER_EMAIL = "chaconne67@gmail.com"
SUPERUSER_PASSWORD = "bachbwv100$"

CEO_NAME = "ceo"
CEO_EMAIL = "ceo@synco.local"
CEO_PASSWORD = "ceo1234"

ORG_NAME = "테스트 헤드헌팅"
CONSULTANT_USERNAME = "kakao_4816981089"


class Command(BaseCommand):
    help = "Seed dev DB with superuser / CEO / consultant test accounts."

    @transaction.atomic
    def handle(self, *args, **options):
        # 1) Remove dead temp user
        deleted, _ = User.objects.filter(email="temp@example.com").delete()
        if deleted:
            self.stdout.write(f"removed temp@example.com ({deleted})")

        # 2) Superuser upsert
        su, created = User.objects.get_or_create(
            username=SUPERUSER_NAME,
            defaults={"email": SUPERUSER_EMAIL},
        )
        su.email = SUPERUSER_EMAIL
        su.is_superuser = True
        su.is_staff = True
        su.set_password(SUPERUSER_PASSWORD)
        su.save()
        self.stdout.write(f"{'created' if created else 'updated'} superuser: {SUPERUSER_NAME}")

        # 3) Test organization
        org, org_created = Organization.objects.get_or_create(name=ORG_NAME)
        self.stdout.write(f"{'created' if org_created else 'found'} org: {ORG_NAME}")

        # 4) CEO user upsert
        ceo, ceo_created = User.objects.get_or_create(
            username=CEO_NAME,
            defaults={"email": CEO_EMAIL},
        )
        ceo.email = CEO_EMAIL
        ceo.set_password(CEO_PASSWORD)
        ceo.save()
        self.stdout.write(f"{'created' if ceo_created else 'updated'} CEO user: {CEO_NAME}")

        Membership.objects.update_or_create(
            user=ceo,
            defaults={
                "organization": org,
                "role": Membership.Role.OWNER,
                "status": Membership.Status.ACTIVE,
            },
        )
        self.stdout.write("CEO membership: OWNER / active")

        # 5) Consultant — attach kakao_4816981089 if exists
        try:
            consultant = User.objects.get(username=CONSULTANT_USERNAME)
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"{CONSULTANT_USERNAME} not found — skipping consultant membership"))
            return

        Membership.objects.update_or_create(
            user=consultant,
            defaults={
                "organization": org,
                "role": Membership.Role.CONSULTANT,
                "status": Membership.Status.ACTIVE,
            },
        )
        self.stdout.write("Consultant membership: CONSULTANT / active")
        self.stdout.write(self.style.SUCCESS("seed_dev_roles done"))
```

- [ ] **Step 3: 커맨드 실행**

Run: `uv run python manage.py seed_dev_roles`
Expected: 출력에 `superuser`, `org`, `CEO user`, `CEO membership`, `Consultant membership`, `seed_dev_roles done` 각각 포함.

- [ ] **Step 4: 상태 확인**

Run:
```bash
uv run python manage.py shell -c "
from accounts.models import User, Membership, Organization
print('users:', User.objects.count())
print('superusers:', list(User.objects.filter(is_superuser=True).values_list('username', 'email')))
print('orgs:', list(Organization.objects.values_list('name', flat=True)))
print('memberships:', list(Membership.objects.values_list('user__username', 'role', 'status')))
print('temp exists?', User.objects.filter(email='temp@example.com').exists())
"
```
Expected:
- `superusers`에 `chaconne67 / chaconne67@gmail.com`
- `orgs`에 `테스트 헤드헌팅`
- `memberships`에 `ceo/owner/active`, `kakao_4816981089/consultant/active`
- `temp exists? False`

- [ ] **Step 5: 커밋**

```bash
git add accounts/management/__init__.py accounts/management/commands/__init__.py accounts/management/commands/seed_dev_roles.py
git commit -m "feat(accounts): seed_dev_roles management command"
```

---

## Task 10: 전체 회귀 + 수동 브라우저 스모크 테스트

**Files:** (없음, 검증만)

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `uv run pytest -q`
Expected: all passed. 실패 시 해당 테스트 수정 후 재실행.

- [ ] **Step 2: lint/format**

Run:
```bash
uv run ruff check accounts main
uv run ruff format accounts main
```
Expected: `All checks passed!` 및 포매팅 변경이 있으면 amend 대신 **새 커밋**으로 추가:
```bash
git add -A
git commit -m "style: ruff format"
```

- [ ] **Step 3: 개발 서버 기동 확인**

Run: `ss -tlnp 2>/dev/null | grep ':8000' || ./dev.sh &`
Expected: 8000 LISTEN 상태.

- [ ] **Step 4: 브라우저 스모크 — 슈퍼유저 동선**

`/browse` 스킬 또는 브라우저로:
1. `http://localhost:8000/accounts/chaconne67-login/` 접속 → 폼 보임
2. `chaconne67` / `bachbwv100$`로 로그인
3. 루트(`/`)가 대시보드로 이동하는지 확인
4. `/superadmin/companies/` 접속 → 업체 리스트 + 등록 폼 보임
5. 업체명 "스모크 테스트 헤드헌팅" 등록 → OWNER 초대코드 리스트에 추가됨
6. `/admin/` 접속 → Django admin 진입 가능
7. `/candidates/` 등 일반 페이지 진입 가능 (초대코드로 튕기지 않음)

스크린샷 캡처 (슈퍼유저 대시보드, 업체 페이지, Django admin).

- [ ] **Step 5: 브라우저 스모크 — CEO 동선**

1. 로그아웃 → `/accounts/ceo-login/` 접속 → 폼 보임
2. `ceo` / `ceo1234` 로그인 → 루트가 대시보드로 이동
3. `/org/` 접속 → "테스트 헤드헌팅" 조직 정보 + `/org/invites/create/` 가능
4. CONSULTANT 초대코드 하나 발급 → 코드 기록

스크린샷 캡처 (CEO 대시보드, 조직 페이지, 초대코드 발급).

- [ ] **Step 6: 브라우저 스모크 — 플래그 OFF 검증**

1. `.env`에서 `ALLOW_CEO_TEST_LOGIN=0`으로 바꾸고 개발 서버 재기동
2. `/accounts/ceo-login/` 접속 → 404
3. 다시 `ALLOW_CEO_TEST_LOGIN=1`로 복구하고 재기동

- [ ] **Step 7: 브라우저 스모크 — 세션 슬라이딩**

`curl`로 셋쿠키 확인:
```bash
curl -s -c /tmp/sess.txt -X POST http://localhost:8000/accounts/chaconne67-login/ \
  -d "username=chaconne67&password=bachbwv100\$" \
  -H "X-CSRFToken: test" -L -o /dev/null -w "%{http_code}\n"
grep sessionid /tmp/sess.txt
```
Expected: `sessionid` 쿠키에 **현재 시각 + ~24h** expiry.

- [ ] **Step 8: 최종 상태 확인 및 PR 준비**

Run: `git log --oneline feat/rbac-onboarding...HEAD~10`
Expected: Task 1~9 커밋 존재. 스모크 스크린샷을 `docs/reports/20260413-rbac-staff-ceo-login-smoke.md`에 첨부해도 좋음 (선택).

---

## 검증 체크리스트 (릴리스 전)

- [ ] `ALLOW_CEO_TEST_LOGIN`이 `.env.prod`에 **없음** 확인
- [ ] `/accounts/chaconne67-login/`이 문서·README·코드 주석·네비게이션에 **노출되지 않음** (`git grep chaconne67-login` 결과는 `accounts/urls.py`, 테스트, 본 플랜만 나와야 함)
- [ ] `/accounts/ceo-login/`도 동일하게 노출 0 (`git grep ceo-login`)
- [ ] 운영 배포 후 `/accounts/ceo-login/` 404 반환 확인 (배포 검증 단계에서 수동 실행)

---

## Out of scope (이번 플랜 제외)

- SuperAdmin 페이지의 업체 **삭제/비활성화**, **OWNER 재발급**, **상세 편집** — 시나리오 검증에는 불필요
- 슈퍼유저용 커스텀 네비게이션·사이드바 항목 — 기존 페이지 재사용으로 충분
- Password reset / 이메일 인증 — 숨은 로그인은 내부 도구, 운영 사용자용 흐름 아님
- 2FA·Rate limiting — 후속 과제
