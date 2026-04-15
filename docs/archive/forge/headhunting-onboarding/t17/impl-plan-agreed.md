# t17: 사이드바 + 모바일 네비게이션 업데이트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사이드바와 모바일 하단 네비게이션에 owner 전용 "조직 관리" 메뉴를 추가한다.

**Design spec:** `docs/forge/headhunting-onboarding/t17/design-spec.md`

**depends_on:** t15

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: Mobile bottom nav layout overflow | CRITICAL | owner 탭 7개 시 min-w-[64px] 제거, px 축소하여 360px 뷰포트 대응 |
| R1-02: No test cases for role-gated nav rendering | CRITICAL | Step 3에 owner/non-owner 네비 렌더링 테스트 추가 |
| R1-03: Step 2 title contradicts body | MAJOR | "replaces reference" 문구 제거. 추가(add)로 명확화 |
| R1-04: --timeout=30 requires pytest-timeout | MAJOR | --timeout=30 제거. `uv run pytest -v` 사용 |
| R1-07: Position inconsistency | MINOR | 사이드바와 모바일 모두 "설정 앞"으로 통일 |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `templates/common/nav_sidebar.html` | 수정 | "조직 관리" 메뉴 추가 (owner 조건부, 설정 앞) |
| `templates/common/nav_bottom.html` | 수정 | 모바일 "조직 관리" 추가 (owner 조건부, 설정 앞) + 레이아웃 대응 |

---

- [ ] **Step 1: Add "조직 관리" menu to nav_sidebar.html (owner only, before settings)**

Before the "설정" menu item, add the org management menu:

```html
  {% if membership and membership.role == 'owner' %}
  <a href="/org/"
     hx-get="/org/" hx-target="#main-content" hx-push-url="true"
     data-nav="org"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
    조직 관리
  </a>
  {% endif %}
```

Update the `updateSidebar()` JavaScript to include the org route. Add this line in the `active` variable computation:

```javascript
                 (key === 'org' && path.startsWith('/org')) ||
```

- [ ] **Step 2: Add "조직 관리" to nav_bottom.html (owner only, before settings) with layout fix**

Before the settings icon, add the org management icon for owner role. Also adjust mobile tab sizing to prevent overflow when owner has 7 tabs — remove `min-w-[64px]` from all owner-visible tabs and reduce horizontal padding:

```html
    {% if membership and membership.role == 'owner' %}
    <a href="/org/"
       hx-get="/org/" hx-target="#main-content" hx-push-url="true"
       data-nav="org"
       class="nav-tab flex flex-col items-center py-1 px-2 text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
      <span class="text-[11px] mt-0.5">조직</span>
    </a>
    {% endif %}
```

**Mobile layout fix for 7-tab owner nav:** Change the existing `min-w-[64px]` to `min-w-0` on ALL nav-tab items, and reduce `px-3` to `px-2` to fit within 360px viewport. The `justify-around` flex layout will distribute space evenly regardless. Update the text size from `text-[12px]` to `text-[11px]` for all tabs to ensure labels don't overflow.

Update the `updateNav()` JavaScript to include the org route:

```javascript
                 (key === 'org' && path.startsWith('/org')) ||
```

- [ ] **Step 3: Add nav rendering tests**

Add tests to verify owner sees the org link and non-owner does not:

```python
# Add to existing test file or create tests/accounts/test_nav_org.py
import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization

User = get_user_model()


@pytest.fixture
def owner_client(db):
    org = Organization.objects.create(name="Test Org")
    owner = User.objects.create_user(username="nav_owner", password="pass")
    Membership.objects.create(user=owner, organization=org, role="owner", status="active")
    client = TestClient()
    client.force_login(owner)
    return client


@pytest.fixture
def consultant_client(db):
    org = Organization.objects.create(name="Test Org")
    consultant = User.objects.create_user(username="nav_cons", password="pass")
    Membership.objects.create(user=consultant, organization=org, role="consultant", status="active")
    client = TestClient()
    client.force_login(consultant)
    return client


@pytest.mark.django_db
class TestNavOrgVisibility:
    def test_owner_sees_org_link_in_nav(self, owner_client):
        response = owner_client.get("/")
        content = response.content.decode()
        assert 'data-nav="org"' in content

    def test_consultant_does_not_see_org_link(self, consultant_client):
        response = consultant_client.get("/")
        content = response.content.decode()
        assert 'data-nav="org"' not in content
```

- [ ] **Step 4: Run tests to verify**

Run: `uv run pytest -v`
Expected: All existing tests still PASS + new nav org visibility tests PASS

- [ ] **Step 5: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html tests/accounts/test_nav_org.py
git commit -m "feat(nav): add org management menu for owner role in sidebar and mobile nav"
```

<!-- forge:t17:impl-plan:complete:2026-04-12T19:30:00+09:00 -->
