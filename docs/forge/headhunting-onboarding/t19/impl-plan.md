# t19: tabChanged 이벤트 시스템 + tab-navigation.js

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tabChanged 커스텀 이벤트 시스템을 구축하고, tab-navigation.js를 생성하여 탭 전환 시 탭바 활성 상태를 자동 갱신하고 뱃지 신규 표시 데이터를 준비한다.

**Design spec:** `docs/forge/headhunting-onboarding/t19/design-spec.md`

**depends_on:** 없음 (Phase 3 첫 번째 태스크)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `static/js/tab-navigation.js` | 생성 | tabChanged 이벤트 핸들러, 뱃지 신규 표시 로직 (sessionStorage) |
| `projects/templates/projects/partials/detail_tab_bar.html` | 수정 | data-tab-bar, data-tab, data-badge-count, data-latest 속성 추가 |
| `projects/templates/projects/project_detail.html` | 수정 | tab-navigation.js script 태그 추가 |
| `projects/views.py` | 수정 | project_detail()에 tab_latest 컨텍스트 추가 |

---

- [ ] **Step 1: tab-navigation.js 생성 — tabChanged 이벤트 핸들러**

```javascript
// static/js/tab-navigation.js

/**
 * tabChanged 이벤트 리스너:
 * HTMX 커스텀 이벤트 "tabChanged"를 수신하여 탭바의 활성 상태를 갱신한다.
 * 이벤트 detail에 { activeTab: "submissions" } 등의 데이터가 포함된다.
 */
document.body.addEventListener("tabChanged", function (e) {
  const activeTab = e.detail.activeTab;
  if (!activeTab) return;

  const tabBar = document.querySelector("[data-tab-bar]");
  if (!tabBar) return;

  // 모든 탭 버튼에서 active 클래스 제거, 해당 탭에 추가
  tabBar.querySelectorAll("[data-tab]").forEach(function (btn) {
    const tab = btn.getAttribute("data-tab");
    if (tab === activeTab) {
      btn.classList.remove("border-transparent", "text-gray-500", "hover:text-gray-700", "hover:border-gray-300");
      btn.classList.add("border-primary", "text-primary");
    } else {
      btn.classList.remove("border-primary", "text-primary");
      btn.classList.add("border-transparent", "text-gray-500", "hover:text-gray-700", "hover:border-gray-300");
    }
  });

  // 뱃지 신규 표시 갱신: 현재 탭의 lastViewed 타임스탬프 업데이트
  const projectPk = document.querySelector("[data-project-pk]")?.getAttribute("data-project-pk");
  if (projectPk) {
    sessionStorage.setItem("lastViewed_" + projectPk + "_" + activeTab, Date.now().toString());
    // 현재 탭의 신규 표시 제거
    const badge = tabBar.querySelector('[data-tab="' + activeTab + '"] [data-badge-new]');
    if (badge) {
      badge.removeAttribute("data-badge-new");
      badge.classList.remove("ring-2", "ring-blue-400");
    }
  }
});

/**
 * 뱃지 신규 표시 초기화:
 * 페이지 로드 시, 각 탭의 최신 항목 생성일(data-latest)과
 * sessionStorage의 lastViewed 타임스탬프를 비교하여 신규 표시를 적용한다.
 */
document.addEventListener("DOMContentLoaded", function () {
  const projectPk = document.querySelector("[data-project-pk]")?.getAttribute("data-project-pk");
  if (!projectPk) return;

  document.querySelectorAll("[data-tab-bar] [data-tab]").forEach(function (btn) {
    const tab = btn.getAttribute("data-tab");
    const badge = btn.querySelector("[data-badge-count]");
    if (!badge) return;

    const latestStr = badge.getAttribute("data-latest");
    if (!latestStr) return;

    const latest = new Date(latestStr).getTime();
    const lastViewed = parseInt(sessionStorage.getItem("lastViewed_" + projectPk + "_" + tab) || "0", 10);

    if (latest > lastViewed) {
      badge.setAttribute("data-badge-new", "true");
      badge.classList.add("ring-2", "ring-blue-400");
    }
  });
});
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

현재 (라인 4-8):
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

동일하게 추천, 면접 뱃지에도 적용. (오퍼 탭은 현재 뱃지가 없으므로 추가 불필요)

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

`projects/views.py`의 `project_detail()` 뷰 (라인 339-345 부근)에 `tab_latest` 데이터를 추가한다.

현재:
```python
    # 탭 배지 카운트
    tab_counts = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }
```

이후에 추가:
```python
    # 탭 뱃지 최신 항목 생성일 (신규 표시용)
    from django.db.models import Max

    tab_latest = {
        "contacts": project.contacts.aggregate(latest=Max("created_at"))["latest"],
        "submissions": project.submissions.aggregate(latest=Max("created_at"))["latest"],
        "interviews": Interview.objects.filter(
            submission__project=project
        ).aggregate(latest=Max("created_at"))["latest"],
    }
```

`render()` 호출에 `"tab_latest": tab_latest` 추가.

- [ ] **Step 5: 수동 검증**

브라우저에서 프로젝트 상세 페이지에 진입하여:
1. 탭바에 `data-tab` 속성이 렌더링되는지 확인
2. 콘솔에서 `document.querySelector('[data-tab-bar]')` 존재 확인
3. `tab-navigation.js`가 로드되는지 Network 탭에서 확인

- [ ] **Step 6: 커밋**

```bash
git add static/js/tab-navigation.js projects/templates/projects/partials/detail_tab_bar.html projects/templates/projects/project_detail.html projects/views.py
git commit -m "feat(projects): add tabChanged event system and tab-navigation.js"
```

<!-- forge:t19:구현계획:draft:2026-04-12 -->
