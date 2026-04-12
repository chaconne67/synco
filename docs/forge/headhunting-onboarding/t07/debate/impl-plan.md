# Task 7: 사이드바 역할별 메뉴 필터링

**Goal:** 사이드바와 모바일 하단 네비게이션에서 역할에 따라 메뉴를 필터링하고, "승인 요청"을 "프로젝트 승인"으로 이름을 변경한다.

**Design spec:** `docs/forge/headhunting-onboarding/t07/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `templates/common/nav_sidebar.html` | 수정 | 역할별 메뉴 필터링, "프로젝트 승인" 이름 변경 |
| `templates/common/nav_bottom.html` | 수정 | 역할별 메뉴 필터링 (모바일) |

---

- [ ] **Step 1: Modify nav_sidebar.html**

Replace the entire content of `templates/common/nav_sidebar.html` with role-based filtering:

- 대시보드, 후보자, 프로젝트, 고객사, 뉴스피드, 설정 -- 모든 역할 표시
- 레퍼런스 -- `{% if membership and membership.role == 'owner' %}` 가드
- 프로젝트 승인 (N) -- owner only, 기존 "승인 요청" 텍스트를 **"프로젝트 승인"**으로 변경
- 조직 관리 -- owner only (신규 항목, `/organization/` URL, 사람 아이콘)

JavaScript `updateSidebar()` 함수에 `organization` key 추가.

- [ ] **Step 2: Update nav_bottom.html similarly**

Apply the same `{% if membership and membership.role == 'owner' %}` guards to the mobile bottom navigation for reference link. (Mobile nav has limited slots -- 조직 관리 등 owner-only 항목은 desktop sidebar에서만 표시.)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html
git commit -m "feat(ui): filter sidebar menus by role, rename approval to project approval"
```
