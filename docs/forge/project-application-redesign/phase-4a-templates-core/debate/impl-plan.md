# Phase 4a — 핵심 레이아웃 템플릿 (대시보드 + 칸반 + 상세 + 카드)

**전제**: [Phase 3b](phase-3b-views-crud.md) 완료. 모든 뷰가 동작하고 템플릿 경로 확정.
**목표**: 대시보드, 2-phase 칸반, 프로젝트 상세 본체, Application 카드, ActionItem 카드 등 **메인 시각 구조**를 구현.
**예상 시간**: 1일
**리스크**: 중 (HTMX 동작)

> **⚠️ 기존 디자인 스타일 유지, UI/UX 변경 최소화**: 현재 구현되어 있는 디자인 스타일을 변경하지 않는다. UI/UX도 데이터 모델 변경에 따라 불가피한 부분만 최소한으로 변경한다.
**범위**: 모달과 후보자 상세 Level 3, 레거시 정리는 [Phase 4b](phase-4b-templates-modals.md).

---

## 1. 목표 상태

- 컨설턴트가 `/dashboard/` → 대시보드 메인 화면 + 오늘 할 일 확인 가능
- `/projects/` → 2-phase 칸반 (서칭/심사/종료) 표시
- `/projects/<id>/` → 상단 요약 + Application 목록 + 각 Application의 ActionItem 패널
- 8개 핵심 템플릿 작성 완료
- Tailwind 빌드 OK, Pretendard 폰트 적용
- 빈 상태(empty state) UI 처리

## 2. 사전 조건

- Phase 3b 커밋 완료
- 모든 뷰가 context를 정상 전달
- Tailwind config가 새 템플릿 경로 포함

## 3. 영향 범위

### 3.1 신규 템플릿
- `projects/templates/projects/dashboard/index.html`
- `projects/templates/projects/partials/dashboard_todo_list.html`
- `projects/templates/projects/project_list.html` (전면 재작성)
- `projects/templates/projects/partials/kanban_column.html`
- `projects/templates/projects/partials/project_card.html`
- `projects/templates/projects/project_detail.html` (전면 재작성)
- `projects/templates/projects/partials/application_card.html`
- `projects/templates/projects/partials/action_item_card.html`

### 3.2 기존 템플릿 (수정 예정, 이 Phase에서)
- `projects/project_list.html` (덮어쓰기)
- `projects/project_detail.html` (덮어쓰기)

### 3.3 Phase 4b로 이월
- 모든 모달 partial
- `partials/view_filters.html` (phase 필터)
- `partials/project_timeline.html`
- `partials/application_actions_list.html`
- `partials/project_applications_list.html`
- 후보자 상세 Level 3 섹션
- 레거시 템플릿 삭제

## 4. 태스크 분할

### T4a.1 — 기존 디자인 스타일 파악
**파일**: 별도 파일 없음
**작업**: 기존 템플릿(`templates/base.html`, 기존 projects 템플릿 등)에서 사용 중인 스타일을 파악하고, 새 템플릿에서 동일한 스타일을 따른다.

기존 base 템플릿에 Pretendard와 Tailwind가 이미 로드되어 있다고 가정.

---

### T4a.2 — `dashboard/index.html` (대시보드 메인)
**파일**: `projects/templates/projects/dashboard/index.html`
**구조**:
```html
{% extends "base.html" %}
{% load static %}

{% block content %}
<div class="min-h-screen bg-slate-950 text-slate-100">
  <header class="px-8 py-6 border-b border-slate-800">
    <h1 class="text-2xl font-semibold">{{ user.get_full_name|default:user.username }}님, 안녕하세요</h1>
    <p class="mt-1 text-sm text-slate-400">
      오늘 할 일 {{ today_actions|length }}건 ·
      마감 지남 {{ overdue_actions|length }}건 ·
      예정 {{ upcoming_actions|length }}건
    </p>
  </header>

  <main class="px-8 py-6 space-y-6">
    {% if overdue_actions %}
      <section class="rounded-2xl border border-red-500/40 bg-red-950/20 p-6">
        <h2 class="text-lg font-semibold text-red-300">⚠ 마감 지남 ({{ overdue_actions|length }})</h2>
        <div class="mt-4 space-y-3">
          {% for action in overdue_actions %}
            {% include "projects/partials/action_item_card.html" with action=action variant="overdue" %}
          {% endfor %}
        </div>
      </section>
    {% endif %}

    <section class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <h2 class="text-lg font-semibold">📌 오늘 할 일 ({{ today_actions|length }})</h2>
      <div class="mt-4 space-y-3">
        {% for action in today_actions %}
          {% include "projects/partials/action_item_card.html" with action=action variant="today" %}
        {% empty %}
          <p class="text-sm text-slate-500">오늘 할 일이 없습니다. 여유로운 하루 보내세요.</p>
        {% endfor %}
      </div>
    </section>

    <section class="rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
      <h2 class="text-lg font-semibold">📅 다가오는 일정 ({{ upcoming_actions|length }})</h2>
      <div class="mt-4 space-y-3">
        {% for action in upcoming_actions %}
          {% include "projects/partials/action_item_card.html" with action=action variant="upcoming" %}
        {% empty %}
          <p class="text-sm text-slate-500">3일 내 예정된 일정이 없습니다.</p>
        {% endfor %}
      </div>
    </section>
  </main>
</div>
{% endblock %}
```

---

### T4a.3 — `partials/dashboard_todo_list.html`
**파일**: `projects/templates/projects/partials/dashboard_todo_list.html`
**작업**: HTMX partial. `actions` context를 받아 `action_item_card.html`로 렌더.

```html
<div class="space-y-3">
  {% for action in actions %}
    {% include "projects/partials/action_item_card.html" with action=action variant=scope %}
  {% empty %}
    <p class="text-sm text-slate-500">표시할 항목이 없습니다.</p>
  {% endfor %}
</div>
```

---

### T4a.4 — `partials/action_item_card.html` (ActionItem 카드)
**파일**: `projects/templates/projects/partials/action_item_card.html`
**구조**:
```html
{% load humanize %}
<div id="action-{{ action.id }}"
     class="rounded-xl border border-slate-800 bg-slate-900/80 p-4
            {% if variant == 'overdue' %}border-red-500/40{% endif %}">
  <div class="flex items-start justify-between gap-4">
    <div class="flex-1">
      <div class="flex items-center gap-2">
        <span class="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
          {{ action.action_type.label_ko }}
        </span>
        {% if action.channel %}
          <span class="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
            {{ action.get_channel_display }}
          </span>
        {% endif %}
      </div>
      <p class="mt-2 text-sm font-medium text-slate-100">{{ action.title }}</p>
      {% if action.application %}
        <p class="mt-1 text-xs text-slate-400">
          <a href="{% url 'projects:project_detail' action.application.project.id %}"
             class="hover:text-teal-300">
            {{ action.application.project.client.name }} · {{ action.application.project.title }}
          </a>
          · {{ action.application.candidate.name }}
        </p>
      {% endif %}
      {% if action.due_at %}
        <p class="mt-2 text-xs {% if variant == 'overdue' %}text-red-300{% else %}text-slate-500{% endif %}">
          마감 {{ action.due_at|naturaltime }}
        </p>
      {% endif %}
      {% if action.note %}
        <p class="mt-1 text-xs text-slate-500">{{ action.note }}</p>
      {% endif %}
      {% if action.status == 'done' and action.result %}
        <p class="mt-2 rounded bg-slate-800/50 p-2 text-xs text-slate-300">
          ✓ {{ action.result }}
        </p>
      {% endif %}
    </div>
    {% if action.status == 'pending' %}
      <div class="flex flex-col gap-2 shrink-0">
        <button hx-post="{% url 'projects:action_complete' action.id %}"
                hx-target="#action-{{ action.id }}"
                hx-swap="outerHTML"
                class="rounded-md bg-teal-600 px-3 py-1 text-xs font-medium text-white hover:bg-teal-500">
          완료
        </button>
        <button hx-post="{% url 'projects:action_skip' action.id %}"
                hx-target="#action-{{ action.id }}"
                hx-swap="outerHTML"
                class="rounded-md bg-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-600">
          건너뛰기
        </button>
      </div>
    {% endif %}
  </div>
</div>
```

---

### T4a.5 — `project_list.html` (2-phase 칸반)
**파일**: `projects/templates/projects/project_list.html`
**구조**:
```html
{% extends "base.html" %}
{% block content %}
<div class="min-h-screen bg-slate-950 text-slate-100">
  <header class="flex items-center justify-between border-b border-slate-800 px-8 py-6">
    <h1 class="text-2xl font-semibold">프로젝트</h1>
    <div class="flex items-center gap-2">
      <a href="{% url 'projects:project_create' %}"
         class="rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500">
        + 새 프로젝트
      </a>
    </div>
  </header>

  {% include "projects/partials/view_filters.html" %}

  <main class="px-8 py-6">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      {% include "projects/partials/kanban_column.html" with title="🔍 서칭" cards=kanban.searching column_key="searching" %}
      {% include "projects/partials/kanban_column.html" with title="📋 심사" cards=kanban.screening column_key="screening" %}
      {% include "projects/partials/kanban_column.html" with title="종료 ▶" cards=kanban.closed column_key="closed" %}
    </div>
  </main>
</div>
{% endblock %}
```

`view_filters.html`은 Phase 4b에서 본격 구현. 여기서는 기존 파일을 placeholder로 사용 가능.

---

### T4a.6 — `partials/kanban_column.html`
**파일**: `projects/templates/projects/partials/kanban_column.html`
**구조**:
```html
<section class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
  <header class="flex items-center justify-between mb-4">
    <h2 class="text-base font-semibold text-slate-200">{{ title }}</h2>
    <span class="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">{{ cards|length }}</span>
  </header>
  <div class="space-y-3 max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
    {% for card in cards %}
      {% include "projects/partials/project_card.html" with card=card column_key=column_key %}
    {% empty %}
      <p class="text-xs text-slate-500">표시할 프로젝트가 없습니다.</p>
    {% endfor %}
  </div>
</section>
```

---

### T4a.7 — `partials/project_card.html`
**파일**: `projects/templates/projects/partials/project_card.html`
**구조**:
```html
{% load humanize %}
<a href="{% url 'projects:project_detail' card.project.id %}"
   class="block rounded-xl border border-slate-800 bg-slate-900/80 p-4 hover:border-teal-500/50 transition">
  <div class="flex items-start justify-between gap-2">
    <div class="flex-1 min-w-0">
      <p class="text-xs text-slate-400 truncate">{{ card.project.client.name }}</p>
      <h3 class="mt-1 text-sm font-semibold text-slate-100 truncate">{{ card.project.title }}</h3>
    </div>
    {% if column_key == "closed" %}
      {% if card.project.result == "success" %}
        <span class="text-emerald-400 text-lg">✅</span>
      {% else %}
        <span class="text-red-400 text-lg">❌</span>
      {% endif %}
    {% endif %}
  </div>
  <div class="mt-3 flex items-center gap-3 text-xs text-slate-400">
    <span>매칭 {{ card.active_count }}건</span>
    {% if card.deadline %}
      {% if card.days_until_deadline < 0 %}
        <span class="text-red-300">마감 지남</span>
      {% elif card.days_until_deadline <= 7 %}
        <span class="text-amber-300">D-{{ card.days_until_deadline }}</span>
      {% else %}
        <span>D-{{ card.days_until_deadline }}</span>
      {% endif %}
    {% endif %}
  </div>
  {% if card.pending_actions_count %}
    <div class="mt-2 text-xs text-slate-400">
      📝 할 일 {{ card.pending_actions_count }}
      {% if card.overdue_count %}
        <span class="text-red-300">(마감 {{ card.overdue_count }})</span>
      {% endif %}
    </div>
  {% endif %}
</a>
```

---

### T4a.8 — `project_detail.html` (프로젝트 상세 메인)
**파일**: `projects/templates/projects/project_detail.html`
**구조**:
```html
{% extends "base.html" %}
{% load humanize %}
{% block content %}
<div class="min-h-screen bg-slate-950 text-slate-100">
  <header class="border-b border-slate-800 px-8 py-6">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="text-sm text-slate-400">{{ project.client.name }}</p>
        <h1 class="mt-1 text-2xl font-semibold">{{ project.title }}</h1>
        <div class="mt-2 flex items-center gap-3 text-xs text-slate-400">
          <span class="rounded-full bg-slate-800 px-2 py-0.5">
            {{ project.get_phase_display }}
          </span>
          <span class="rounded-full bg-slate-800 px-2 py-0.5">
            {{ project.get_status_display }}
          </span>
          {% if project.deadline %}
            <span>마감 {{ project.deadline|date:"Y-m-d" }}</span>
          {% endif %}
          <span>매칭 {{ applications|length }}건</span>
        </div>
      </div>
      <div class="flex flex-col gap-2 items-end">
        <button hx-get="{% url 'projects:project_add_candidate' project.id %}"
                hx-target="#modal-container"
                hx-swap="innerHTML"
                class="rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500">
          + 후보자 추가
        </button>
        <a href="{% url 'projects:project_edit' project.id %}"
           class="text-xs text-slate-400 hover:text-slate-200">JD 편집</a>
        {% if project.status == "open" %}
          <button hx-get="#"
                  class="text-xs text-slate-400 hover:text-red-300">프로젝트 종료</button>
        {% endif %}
      </div>
    </div>
  </header>

  <main class="px-8 py-6">
    <h2 class="mb-4 text-base font-semibold text-slate-200">매칭된 후보자</h2>
    <div class="space-y-3">
      {% for application in applications %}
        {% include "projects/partials/application_card.html" with application=application %}
      {% empty %}
        <p class="text-sm text-slate-500">아직 매칭된 후보자가 없습니다. 우측 상단의 [후보자 추가] 버튼을 사용하세요.</p>
      {% endfor %}
    </div>
  </main>

  <div id="modal-container"></div>
</div>
{% endblock %}
```

---

### T4a.9 — `partials/application_card.html`
**파일**: `projects/templates/projects/partials/application_card.html`
**구조**:
```html
{% load humanize %}
<div id="application-{{ application.id }}"
     class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5
            {% if application.dropped_at %}opacity-60{% endif %}">
  <div class="flex items-start justify-between gap-4">
    <div class="flex-1 min-w-0">
      <a href="{% url 'candidates:candidate_detail' application.candidate.id %}"
         class="text-base font-semibold text-slate-100 hover:text-teal-300">
        {{ application.candidate.name }}
      </a>
      <p class="mt-1 text-xs text-slate-400">
        {% if application.candidate.birth_year %}{{ application.candidate.birth_year }}년생 · {% endif %}
        {% if application.candidate.current_company %}{{ application.candidate.current_company }} · {% endif %}
        매칭 {{ application.created_at|naturaltime }}
      </p>
      <p class="mt-1 text-xs text-slate-500">
        상태: <span class="text-slate-300">{{ application.current_state }}</span>
      </p>

      {% if application.dropped_at %}
        <div class="mt-3 rounded-md border border-red-500/30 bg-red-950/20 p-3 text-xs text-red-300">
          드롭됨 ({{ application.get_drop_reason_display }})
          {% if application.drop_note %}<p class="mt-1 text-red-400">{{ application.drop_note }}</p>{% endif %}
        </div>
      {% else %}
        <div class="mt-4 space-y-2">
          {% for action in application.action_items.all %}
            {% if action.status == "pending" %}
              {% include "projects/partials/action_item_card.html" with action=action %}
            {% endif %}
          {% endfor %}
        </div>
      {% endif %}
    </div>

    <div class="flex flex-col gap-2 shrink-0">
      {% if application.dropped_at %}
        <button hx-post="{% url 'projects:application_restore' application.id %}"
                hx-target="#application-{{ application.id }}"
                hx-swap="outerHTML"
                class="rounded-md bg-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-600">
          복구
        </button>
      {% else %}
        <button hx-get="{% url 'projects:action_create' application.id %}"
                hx-target="#modal-container"
                hx-swap="innerHTML"
                class="rounded-md bg-teal-700 px-3 py-1 text-xs text-white hover:bg-teal-600">
          + 액션
        </button>
        <button hx-get="#"
                class="rounded-md bg-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-600">
          드롭
        </button>
      {% endif %}
    </div>
  </div>
</div>
```

---

### T4a.10 — Tailwind 빌드 + 기동 확인
**작업**:
```bash
./dev.sh
# 또는
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch
```

다른 터미널에서:
```bash
uv run python manage.py runserver 0.0.0.0:8000
```

**수동 확인** (브라우저):
- `/dashboard/` → 빈 상태 메시지 표시 (Application 없음)
- `/projects/` → 3컬럼 칸반 (빈 상태)
- `/projects/<id>/` → 상단 요약 + "아직 매칭된 후보자가 없습니다"
- 관리자에서 Application 1건 생성 후 상세 페이지에 카드 표시 확인

---

## 5. 검증 체크리스트

- [ ] `dashboard/index.html` 렌더링 + 빈 상태 메시지
- [ ] `dashboard_todo_list.html` partial 동작
- [ ] `project_list.html` 3컬럼 칸반 표시
- [ ] `kanban_column.html`, `project_card.html` partial 정상
- [ ] `project_detail.html` 상단 요약 + Application 목록
- [ ] `application_card.html` 정상 (드롭 상태도)
- [ ] `action_item_card.html` 완료/건너뛰기 버튼 클릭 가능
- [ ] Tailwind 클래스가 빌드되어 시각적으로 적용
- [ ] HTMX 액션 완료 클릭 시 카드 swap 동작 (200 응답, 후속 모달은 Phase 4b에서 완성)

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `application.current_state` property가 ActionItem 쿼리를 발생 → N+1 | `prefetch_related("action_items__action_type")` 사용 (Phase 3a `project_detail` 뷰에서 이미 적용) |
| 액션 카드의 시간 표시 (humanize) 한국어 미적용 | `LANGUAGE_CODE = "ko-kr"` settings 확인. 필요 시 커스텀 필터 |
| 모달 컨테이너 (`#modal-container`)가 base.html에 없음 | `base.html`에 `<div id="modal-container"></div>` 추가 |
| 기존 `view_filters.html`이 ProjectStatus 기반이라 import 시 깨짐 | Phase 4a에서는 빈 placeholder로 교체. Phase 4b에서 본격 구현 |
| 캔들레이트 모델의 필드명(`birth_year`, `current_company`) 실제와 다름 | candidates/models.py 확인 후 정확한 필드명 사용. 없으면 생략 |
| 새 템플릿 스타일이 기존 페이지와 불일치 | 기존 템플릿의 스타일을 그대로 따른다 |

## 7. 커밋 포인트

```
feat(projects): build core dashboard/kanban/detail templates

- Add dashboard/index.html with today/overdue/upcoming sections
- Rebuild project_list.html as 2-phase + closed kanban
- Rebuild project_detail.html with Application card list
- Add kanban_column, project_card, application_card, action_item_card partials
- Stellate dark navy styling, Pretendard, HTMX swap targets

Refs: FINAL-SPEC.md §5
```

## 8. Phase 4b로 넘기는 인터페이스

- 메인 시각 구조 확립 (기존 디자인 스타일 유지)
- HTMX 모달 트리거 버튼은 `#modal-container`로 swap (Phase 4b가 모달 partial 작성)
- Application/ActionItem 카드의 인터랙션 흐름이 Phase 4b 모달과 자연스럽게 이어지도록 hx-target/swap 일관성 유지

---

**이전 Phase**: [phase-3b-views-crud.md](phase-3b-views-crud.md)
**다음 Phase**: [phase-4b-templates-modals.md](phase-4b-templates-modals.md)
