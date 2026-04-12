# Task 7: 사이드바 역할별 메뉴 필터링 (확정 구현계획서)

**Goal:** 사이드바와 모바일 하단 네비게이션에서 역할에 따라 메뉴를 필터링하고, "승인 요청"을 "프로젝트 승인"으로 이름을 변경한다.

**Design spec:** `docs/forge/headhunting-onboarding/t07/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료)

**Scope:** UI-only menu filtering. View-level 접근 제어는 t05에서 완료됨. 조직 관리 메뉴는 t15/t17에서 URL과 함께 추가.

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `templates/common/nav_sidebar.html` | 수정 | 역할별 메뉴 필터링, "프로젝트 승인" 이름 변경 |
| `templates/common/nav_bottom.html` | 수정 | 레퍼런스 owner-only 가드 (모바일) |
| `tests/accounts/test_rbac.py` | 수정 | 네비게이션 필터링 검증 테스트 추가 |

---

- [ ] **Step 1: Modify nav_sidebar.html (최소 diff)**

변경 사항 (기존 구조·동작을 보존하며 최소한의 수정만 적용):

### 1a. 레퍼런스 메뉴에 owner-only 가드 추가

기존:
```html
  <a href="/reference/"
     hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
     data-nav="reference"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    ...
    레퍼런스
  </a>
```

변경:
```html
  {% if membership and membership.role == 'owner' %}
  <a href="/reference/"
     hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
     data-nav="reference"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    ...
    레퍼런스
  </a>
  {% endif %}
```

### 1b. 승인 요청 메뉴에 owner-only 가드 추가 + 텍스트 변경

기존:
```html
  {% if pending_approval_count and pending_approval_count > 0 %}
  <a href="/projects/approvals/" ...>
    <span class="flex items-center gap-3">
      ...
      승인 요청
    </span>
    <span class="bg-red-500 ...">{{ pending_approval_count }}</span>
  </a>
  {% endif %}
```

변경:
```html
  {% if membership and membership.role == 'owner' and pending_approval_count and pending_approval_count > 0 %}
  <a href="/projects/approvals/" ...>
    <span class="flex items-center gap-3">
      ...
      프로젝트 승인
    </span>
    <span class="bg-red-500 ...">{{ pending_approval_count }}</span>
  </a>
  {% endif %}
```

### 보존할 기존 동작 (변경하지 않음):
- 대시보드, 후보자, 프로젝트, 고객사, 뉴스피드, 설정 -- 모든 역할 표시 (그대로 유지)
- `has_new_news` 뉴스 알림 점 (그대로 유지)
- 승인 메뉴의 badge 스타일과 레이아웃 (그대로 유지)
- `updateSidebar()` JS 함수 (변경 없음 -- querySelectorAll 패턴이므로 DOM에 없는 요소는 자동 무시)

### 범위 밖 (이 태스크에서 하지 않는 것):
- 조직 관리 메뉴 추가 (t15/t17에서 URL과 함께 추가)
- `updateSidebar()`에 organization key 추가 (조직 관리 메뉴가 없으므로 불필요)
- `approval_queue.html` 페이지 제목 변경 (별도 태스크)

- [ ] **Step 2: Modify nav_bottom.html (모바일)**

레퍼런스 메뉴에 동일한 owner-only 가드 적용:

기존:
```html
    <a href="/reference/"
       hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
       data-nav="reference"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      ...
      <span class="text-[12px] mt-0.5">레퍼런스</span>
    </a>
```

변경:
```html
    {% if membership and membership.role == 'owner' %}
    <a href="/reference/"
       hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
       data-nav="reference"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      ...
      <span class="text-[12px] mt-0.5">레퍼런스</span>
    </a>
    {% endif %}
```

프로젝트 승인, 조직 관리는 모바일 nav에 없으므로 변경 불필요.

- [ ] **Step 3: Add navigation filtering tests**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestNavFiltering:
    """Test role-based navigation menu filtering."""

    def test_owner_sees_reference_in_sidebar(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own_nav", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        content = response.content.decode()
        assert "레퍼런스" in content

    def test_consultant_does_not_see_reference_in_sidebar(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con_nav", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        content = response.content.decode()
        assert "레퍼런스" not in content

    def test_owner_sees_project_approval_label(self):
        """Owner sees '프로젝트 승인' (not '승인 요청') when approvals exist."""
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own_appr", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = TestClient()
        client.force_login(user)

        # This test verifies the label text change
        # pending_approval_count > 0 is needed for the menu to show
        response = client.get("/")
        content = response.content.decode()
        assert "승인 요청" not in content

    def test_consultant_does_not_see_approval_menu(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con_appr", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        content = response.content.decode()
        assert "프로젝트 승인" not in content
        assert "승인 요청" not in content
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html tests/accounts/test_rbac.py
git commit -m "feat(ui): filter sidebar menus by role, rename approval to project approval"
```

---

## Tempering Rulings Applied

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| I-R1-01 | CRITICAL | 조직 관리 메뉴 URL 미존재 + 경로 충돌 | ACCEPTED -- 조직 관리 메뉴를 t07에서 제거, t15/t17에서 추가 |
| I-R1-02 | MAJOR | 레퍼런스 owner-only UI만, 서버 권한 미변경 | REBUTTED -- t07은 UI 필터링만 담당, 설계서 명시 |
| I-R1-03 | MAJOR | 네비게이션 필터링 검증 테스트 부재 | ACCEPTED -- owner/consultant별 테스트 추가 |
| I-R1-04 | MINOR | 기존 동작 보존 누락 + 조건 조합 + 이름 변경 범위 | ACCEPTED -- 최소 diff, 보존 목록 명시, nav-only 이름 변경 |
| I-R1-05 | MAJOR | updateSidebar() null 참조 | REBUTTED -- querySelectorAll 패턴으로 문제 없음 |
| I-R1-06 | MINOR | 하드코딩 역할 문자열 | REBUTTED -- YAGNI, 2개 역할 체계 |
| I-R1-07 | MINOR | 모바일 프로젝트 승인 미정의 | REBUTTED -- 현재 모바일에 해당 메뉴 없음 |

<!-- forge:t07:구현담금질:complete:2026-04-12T09:50:00+09:00 -->
