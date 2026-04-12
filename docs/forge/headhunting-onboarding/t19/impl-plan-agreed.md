# t19: tabChanged 이벤트 시스템 + tab-navigation.js

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tabChanged 커스텀 이벤트 시스템을 구축하고, tab-navigation.js를 생성하여 탭 전환 시 탭바 활성 상태를 자동 갱신하고 뱃지 신규 표시 데이터를 준비한다.

**Design spec:** `docs/forge/headhunting-onboarding/t19/design-spec.md`

**depends_on:** t18

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: tabChanged event is never dispatched | CRITICAL | PARTIAL — Design spec scopes t19 as infrastructure only; dispatching is t20/t21/t23. Gap for regular tab bar clicks documented as upstream note. |
| R1-02: DOMContentLoaded fails on HTMX navigation | CRITICAL | ACCEPTED — Rewrote JS to use IIFE + htmx:afterSettle + readyState pattern |
| R1-03: Duplicate event listener registration | MAJOR | ACCEPTED — Wrapped in IIFE with cleanup, following context-autosave.js pattern |
| R1-04: project_delete() error path missing tab_latest | MAJOR | ACCEPTED — Added _build_tab_context() helper used by both views |
| R1-05: Manual verification too weak | MAJOR | ACCEPTED — Expanded verification to test actual behavior |
| R1-06: Import style — local import | MINOR | ACCEPTED — Moved Max to top-level import |
| R1-07: offers missing from tab_latest | MINOR | ACCEPTED — Added offers to tab_latest |
| R1-08: Line reference inaccuracy | MINOR | ACCEPTED — Corrected line references |
| R1-09: depends_on mismatch | MINOR | ACCEPTED — Corrected to t18 |

---

## Known Limitations / Upstream Notes

> **Regular tab bar button clicks do not dispatch `tabChanged`.** No downstream task (t20, t21, t23) covers this path — they only dispatch from specific workflow flows (submission success, banner CTA, funnel links). This means regular tab bar clicks will continue to rely on Django's server-rendered `{% if active == ... %}` for initial state, and HTMX swaps won't update the tab bar active state for basic tab navigation. Consider addressing in t23 (which already uses `hx-on::after-request`) or t25 (integration test).

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `static/js/tab-navigation.js` | 생성 | tabChanged 이벤트 핸들러, 뱃지 신규 표시 로직 (sessionStorage), IIFE + htmx:afterSettle 패턴 |
| `projects/templates/projects/partials/detail_tab_bar.html` | 수정 | data-tab-bar, data-tab, data-badge-count, data-latest 속성 추가 |
| `projects/templates/projects/project_detail.html` | 수정 | tab-navigation.js script 태그 추가 |
| `projects/views.py` | 수정 | _build_tab_context() 헬퍼 추가, project_detail() + project_delete()에 tab_latest 컨텍스트 추가 |

---

- [ ] **Step 1: tab-navigation.js 생성 — IIFE + htmx:afterSettle 패턴**

```javascript
// static/js/tab-navigation.js

(function () {
  "use strict";

  var _tabChangedHandler = null;
  var _afterSettleHandler = null;

  function initTabBadges() {
    var projectPk = document.querySelector("[data-project-pk]");
    if (!projectPk) return;
    projectPk = projectPk.getAttribute("data-project-pk");

    document.querySelectorAll("[data-tab-bar] [data-tab]").forEach(function (btn) {
      var tab = btn.getAttribute("data-tab");
      var badge = btn.querySelector("[data-badge-count]");
      if (!badge) return;

      var latestStr = badge.getAttribute("data-latest");
      if (!latestStr) return;

      var latest = new Date(latestStr).getTime();
      var lastViewed = parseInt(
        sessionStorage.getItem("lastViewed_" + projectPk + "_" + tab) || "0",
        10
      );

      if (latest > lastViewed) {
        badge.setAttribute("data-badge-new", "true");
        badge.classList.add("ring-2", "ring-blue-400");
      }
    });
  }

  function handleTabChanged(e) {
    var activeTab = e.detail.activeTab;
    if (!activeTab) return;

    var tabBar = document.querySelector("[data-tab-bar]");
    if (!tabBar) return;

    // 모든 탭 버튼에서 active 클래스 제거, 해당 탭에 추가
    tabBar.querySelectorAll("[data-tab]").forEach(function (btn) {
      var tab = btn.getAttribute("data-tab");
      if (tab === activeTab) {
        btn.classList.remove(
          "border-transparent",
          "text-gray-500",
          "hover:text-gray-700",
          "hover:border-gray-300"
        );
        btn.classList.add("border-primary", "text-primary");
      } else {
        btn.classList.remove("border-primary", "text-primary");
        btn.classList.add(
          "border-transparent",
          "text-gray-500",
          "hover:text-gray-700",
          "hover:border-gray-300"
        );
      }
    });

    // 뱃지 신규 표시 갱신: 현재 탭의 lastViewed 타임스탬프 업데이트
    var projectEl = document.querySelector("[data-project-pk]");
    var projectPk = projectEl ? projectEl.getAttribute("data-project-pk") : null;
    if (projectPk) {
      sessionStorage.setItem(
        "lastViewed_" + projectPk + "_" + activeTab,
        Date.now().toString()
      );
      // 현재 탭의 신규 표시 제거
      var badge = tabBar.querySelector(
        '[data-tab="' + activeTab + '"] [data-badge-new]'
      );
      if (badge) {
        badge.removeAttribute("data-badge-new");
        badge.classList.remove("ring-2", "ring-blue-400");
      }
    }
  }

  function cleanup() {
    if (_tabChangedHandler) {
      document.body.removeEventListener("tabChanged", _tabChangedHandler);
      _tabChangedHandler = null;
    }
  }

  function init() {
    cleanup();
    _tabChangedHandler = handleTabChanged;
    document.body.addEventListener("tabChanged", _tabChangedHandler);
    initTabBadges();
  }

  // Re-initialize after HTMX swaps
  _afterSettleHandler = function () {
    // Only re-init if project detail page is present
    if (document.querySelector("[data-tab-bar]")) {
      init();
    }
  };
  document.addEventListener("htmx:afterSettle", _afterSettleHandler);

  // Initial setup
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

- [ ] **Step 2: detail_tab_bar.html에 data 속성 추가**

`detail_tab_bar.html`을 수정하여 각 버튼에 `data-tab` 속성, 컨테이너에 `data-tab-bar` 속성, 뱃지에 `data-badge-count`와 `data-latest` 속성을 추가한다.

현재 코드 (라인 1):
```html
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8">
```

변경:
```html
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8" data-tab-bar>
```

각 `<button>`에 `data-tab` 속성을 추가한다. 예를 들어 개요 탭:

현재 (라인 4-9):
```html
  <button hx-get="{% url 'projects:project_tab_overview' project.pk %}"
          hx-target="#tab-content"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'overview' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    개요
  </button>
```

변경:
```html
  <button data-tab="overview"
          hx-get="{% url 'projects:project_tab_overview' project.pk %}"
          hx-target="#tab-content"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'overview' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    개요
  </button>
```

동일하게 나머지 5개 탭 버튼에도 `data-tab="search"`, `data-tab="contacts"`, `data-tab="submissions"`, `data-tab="interviews"`, `data-tab="offers"`를 추가한다.

뱃지 span에 `data-badge-count`와 `data-latest` 추가. 예시 (컨택 탭 뱃지):

현재:
```html
    <span class="text-[11px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">{{ tab_counts.contacts }}</span>
```

변경:
```html
    <span class="text-[11px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full"
          data-badge-count
          data-latest="{{ tab_latest.contacts|date:'c' }}">{{ tab_counts.contacts }}</span>
```

동일하게 추천(`tab_latest.submissions`), 면접(`tab_latest.interviews`) 뱃지에도 적용. (오퍼 탭은 현재 뱃지가 없으므로 추가 불필요)

- [ ] **Step 3: project_detail.html에 tab-navigation.js 로드 추가**

현재 (라인 77-78):
```html
{% load static %}
<script src="{% static 'js/context-autosave.js' %}"></script>
```

변경:
```html
{% load static %}
<script src="{% static 'js/context-autosave.js' %}"></script>
<script src="{% static 'js/tab-navigation.js' %}"></script>
```

- [ ] **Step 4: project_detail 뷰에 tab_latest 컨텍스트 추가**

**4a: Top-level import 추가**

`projects/views.py` 라인 7의 기존 import:
```python
from django.db.models import Count, Q
```

변경:
```python
from django.db.models import Count, Max, Q
```

**4b: _build_tab_context() 헬퍼 함수 추가**

`project_detail()` 함수 직전 (라인 348 부근)에 헬퍼를 추가한다:

```python
def _build_tab_context(project):
    """Build tab_counts and tab_latest for project detail template."""
    tab_counts = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }
    tab_latest = {
        "contacts": project.contacts.aggregate(latest=Max("created_at"))["latest"],
        "submissions": project.submissions.aggregate(latest=Max("created_at"))["latest"],
        "interviews": Interview.objects.filter(
            submission__project=project
        ).aggregate(latest=Max("created_at"))["latest"],
        "offers": Offer.objects.filter(
            submission__project=project
        ).aggregate(latest=Max("created_at"))["latest"],
    }
    return tab_counts, tab_latest
```

**4c: project_detail() 수정**

현재 (라인 353-359):
```python
    # 탭 배지 카운트
    tab_counts = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }
```

변경:
```python
    tab_counts, tab_latest = _build_tab_context(project)
```

`render()` 호출 (라인 364-373)에 `"tab_latest": tab_latest` 추가:
```python
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "tab_counts": tab_counts,
            "tab_latest": tab_latest,
            "active_tab": "overview",
            **overview_context,
        },
    )
```

**4d: project_delete() 수정**

현재 (라인 421-426):
```python
        tab_counts = {
            "contacts": project.contacts.count(),
            "submissions": project.submissions.count(),
            "interviews": Interview.objects.filter(submission__project=project).count(),
            "offers": Offer.objects.filter(submission__project=project).count(),
        }
```

변경:
```python
        tab_counts, tab_latest = _build_tab_context(project)
```

`render()` 호출 (라인 428-438)에 `"tab_latest": tab_latest` 추가:
```python
        return render(
            request,
            "projects/project_detail.html",
            {
                "project": project,
                "tab_counts": tab_counts,
                "tab_latest": tab_latest,
                "active_tab": "overview",
                "error_message": "컨택 또는 제출 이력이 있어 삭제할 수 없습니다.",
                **overview_context,
            },
        )
```

- [ ] **Step 5: 수동 검증**

브라우저에서 프로젝트 상세 페이지에 진입하여:
1. 탭바에 `data-tab` 속성이 렌더링되는지 확인
2. 콘솔에서 `document.querySelector('[data-tab-bar]')` 존재 확인
3. `tab-navigation.js`가 로드되는지 Network 탭에서 확인
4. 콘솔에서 tabChanged 이벤트를 수동 발행하여 active 클래스 변경 확인:
   ```javascript
   document.body.dispatchEvent(new CustomEvent("tabChanged", { detail: { activeTab: "contacts" } }));
   ```
5. `sessionStorage.getItem('lastViewed_<project_pk>_contacts')` 값이 업데이트되었는지 확인
6. 뱃지에 `ring-2 ring-blue-400` 클래스가 추가/제거되는지 확인
7. HTMX 네비게이션으로 프로젝트 목록 → 상세 진입 후 뱃지 초기화가 동작하는지 확인

- [ ] **Step 6: 커밋**

```bash
git add static/js/tab-navigation.js projects/templates/projects/partials/detail_tab_bar.html projects/templates/projects/project_detail.html projects/views.py
git commit -m "feat(projects): add tabChanged event system and tab-navigation.js"
```

<!-- forge:t19:impl-plan:complete:2026-04-12T22:10:00+09:00 -->
