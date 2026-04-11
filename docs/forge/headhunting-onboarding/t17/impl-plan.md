# t17: 사이드바 + 모바일 네비게이션 업데이트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사이드바와 모바일 하단 네비게이션에 owner 전용 "조직 관리" 메뉴를 추가한다.

**Design spec:** `docs/forge/headhunting-onboarding/t17/design-spec.md`

**depends_on:** t15

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `templates/common/nav_sidebar.html` | 수정 | "조직 관리" 메뉴 추가 (owner 조건부) |
| `templates/common/nav_bottom.html` | 수정 | 모바일 "조직 관리" 추가 (owner 조건부) |

---

- [ ] **Step 1: Add "조직 관리" menu to nav_sidebar.html (owner only)**

After the "설정" menu item (before `<script>`), add the org management menu:

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

Update the `updateSidebar()` JavaScript to include the org route:

```javascript
                 (key === 'org' && path.startsWith('/org')) ||
```

- [ ] **Step 2: Add "조직 관리" to nav_bottom.html (owner only, replaces reference on mobile)**

Since mobile bottom nav has limited space, add the org management icon only for owner role. Add before the settings icon:

```html
    {% if membership and membership.role == 'owner' %}
    <a href="/org/"
       hx-get="/org/" hx-target="#main-content" hx-push-url="true"
       data-nav="org"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
      <span class="text-[12px] mt-0.5">조직</span>
    </a>
    {% endif %}
```

Update the `updateNav()` JavaScript to include the org route:

```javascript
                 (key === 'org' && path.startsWith('/org')) ||
```

- [ ] **Step 3: Verify sidebar rendering**

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 4: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html
git commit -m "feat(nav): add org management menu for owner role in sidebar and mobile nav"
```
