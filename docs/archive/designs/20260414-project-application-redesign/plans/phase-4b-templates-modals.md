# Phase 4b — 모달 + 후보자 상세 + 필터바 + 레거시 정리

**전제**: [Phase 4a](phase-4a-templates-core.md) 완료. 메인 시각 구조와 카드가 동작.
**목표**: 모든 모달(액션 생성/완료/제안/드롭/프로젝트 종료/후보자 추가), 필터 바, 타임라인, 후보자 상세 Level 3 섹션을 구현. 레거시 템플릿(`tab_offers`, `dash_full`, `dash_pipeline`, `view_board_card`, `kanban.js`)을 완전 삭제.
**예상 시간**: 0.5-1일
**리스크**: 중

---

## 1. 목표 상태

- 모든 모달이 HTMX로 열리고 form submit 후 카드 swap이 자연스럽게 동작
- `view_filters.html`이 phase 필터 + 담당자/고객사/기간 필터 제공
- `project_timeline.html`이 ActionItem 시계열 표시
- 후보자 상세 페이지(Level 3)에 해당 후보자의 모든 Application 섹션 추가
- 레거시 템플릿 6+개 파일 삭제
- `kanban.js` 제거 또는 비활성화
- 브라우저에서 전체 플로우 수동 확인 (Application 추가 → ActionItem 완료 → 후속 제안 → 드롭 → 종료)

## 2. 사전 조건

- Phase 4a 커밋 완료
- 디자인 토큰(다크 네이비) 확립
- `#modal-container`가 base.html 또는 project_detail.html에 존재

## 3. 영향 범위

### 3.1 신규 템플릿
- `projects/templates/projects/partials/add_candidate_modal.html`
- `projects/templates/projects/partials/action_create_modal.html`
- `projects/templates/projects/partials/action_complete_modal.html`
- `projects/templates/projects/partials/action_propose_next_modal.html`
- `projects/templates/projects/partials/drop_application_modal.html`
- `projects/templates/projects/partials/project_close_modal.html`
- `projects/templates/projects/partials/project_timeline.html`
- `projects/templates/projects/partials/application_actions_list.html`
- `projects/templates/projects/partials/project_applications_list.html`
- `projects/templates/projects/partials/view_filters.html` (재작성)

### 3.2 수정 템플릿
- `candidates/templates/candidates/candidate_detail.html` (Application 섹션 추가)
- `templates/base.html` 또는 유사 base — `#modal-container` 위치 확정

### 3.3 삭제 템플릿
- `projects/templates/projects/partials/tab_offers.html`
- `projects/templates/projects/partials/dash_full.html`
- `projects/templates/projects/partials/dash_pipeline.html`
- `projects/templates/projects/partials/view_board_card.html`
- 기타 status_update, offer 관련 partial (grep으로 발견)

### 3.4 정적 자산 정리
- `projects/static/js/kanban.js` 삭제 또는 비우기

## 4. 태스크 분할

### T4b.1 — 모달 공용 컨벤션
**작업**: 모달 partial 공통 구조 결정.

```html
<!-- 모달 컨테이너에 swap되는 내용 -->
<div id="modal-overlay"
     class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm"
     hx-on:click="if (event.target === this) document.getElementById('modal-container').innerHTML = ''">
  <div class="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
    <header class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-100">{{ modal_title }}</h2>
      <button onclick="document.getElementById('modal-container').innerHTML = ''"
              class="text-slate-500 hover:text-slate-300">✕</button>
    </header>
    <!-- 모달 내용 -->
  </div>
</div>
```

각 모달 파일이 이 구조를 사용. 닫기 버튼은 `#modal-container`를 비우는 방식.

---

### T4b.2 — `partials/add_candidate_modal.html`
**파일**: `projects/templates/projects/partials/add_candidate_modal.html`
**구조**:
```html
<div id="modal-overlay"
     class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
  <div class="w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 p-6">
    <header class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold">후보자 추가</h2>
      <button onclick="document.getElementById('modal-container').innerHTML = ''"
              class="text-slate-500 hover:text-slate-300">✕</button>
    </header>

    <!-- 탭 -->
    <div class="mb-4 flex gap-1 border-b border-slate-800">
      <button type="button"
              class="border-b-2 border-teal-500 px-4 py-2 text-sm text-teal-300">
        DB 검색
      </button>
      <button type="button"
              class="px-4 py-2 text-sm text-slate-500"
              disabled>
        파일 업로드 (준비 중)
      </button>
      <button type="button"
              class="px-4 py-2 text-sm text-slate-500"
              disabled>
        Drive (준비 중)
      </button>
      <button type="button"
              class="px-4 py-2 text-sm text-slate-500"
              disabled>
        이메일 (준비 중)
      </button>
      <button type="button"
              class="px-4 py-2 text-sm text-slate-500"
              disabled>
        음성 (준비 중)
      </button>
    </div>

    <form hx-post="{% url 'projects:project_add_candidate' project.id %}"
          hx-target="#modal-container"
          hx-swap="innerHTML">
      {% csrf_token %}
      <div class="space-y-3">
        <label class="block">
          <span class="text-sm text-slate-300">후보자 선택</span>
          {{ form.candidate }}
        </label>
        <label class="block">
          <span class="text-sm text-slate-300">메모 (선택)</span>
          {{ form.notes }}
        </label>
        {% if form.candidate.errors %}
          <p class="text-xs text-red-400">{{ form.candidate.errors.0 }}</p>
        {% endif %}
      </div>
      <div class="mt-6 flex justify-end gap-2">
        <button type="button"
                onclick="document.getElementById('modal-container').innerHTML = ''"
                class="rounded-md bg-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-600">
          취소
        </button>
        <button type="submit"
                class="rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500">
          추가
        </button>
      </div>
    </form>
  </div>
</div>
```

**참고**: 파일 업로드/Drive/이메일/음성 탭은 v1에서 비활성. 향후 확장 자리만 마련.

---

### T4b.3 — `partials/action_create_modal.html`
**파일**: `projects/templates/projects/partials/action_create_modal.html`
**작업**:
- action_type select (active만)
- title input (선택, 자동 생성 가능)
- channel select
- scheduled_at, due_at datetime-local
- note textarea
- 제출 시 `hx-post="{% url 'projects:action_create' application.id %}"`

(템플릿 본문은 add_candidate_modal과 유사 구조, 필드만 다름)

---

### T4b.4 — `partials/action_complete_modal.html`
**파일**: `projects/templates/projects/partials/action_complete_modal.html`
**작업**:
- result textarea
- note textarea
- next_action 체크박스 목록 (action_type.suggests_next 기반, 서버에서 미리 계산해서 context로 전달)
- 제출 시 `hx-post="{% url 'projects:action_complete' action.id %}"`
- 응답이 후속 제안 모달이므로 `hx-target="#modal-container"`

---

### T4b.5 — `partials/action_propose_next_modal.html`
**파일**: `projects/templates/projects/partials/action_propose_next_modal.html`
**작업**:
- 완료된 액션 정보 표시
- 제안된 ActionType 체크박스 목록
- "이 중 어떤 액션을 다음에 진행할까요?" 안내
- 각 체크박스 옆에 due_at 입력 (선택)
- 제출 시 `hx-post="{% url 'projects:action_propose_next' action.id %}"`
- "건너뛰기" 버튼: 모달 닫기

---

### T4b.6 — `partials/drop_application_modal.html`
**파일**: `projects/templates/projects/partials/drop_application_modal.html`
**작업**:
- drop_reason 라디오 (4개 enum, label은 한국어)
- drop_note textarea
- 제출 시 `hx-post="{% url 'projects:application_drop' application.id %}"`

---

### T4b.7 — `partials/project_close_modal.html`
**파일**: `projects/templates/projects/partials/project_close_modal.html`
**작업**:
- result 라디오 (success/fail)
- note textarea (필수)
- 활성 Application 수 경고 메시지 (있으면)
- 제출 시 `hx-post="{% url 'projects:project_close' project.id %}"`

---

### T4b.8 — `partials/project_timeline.html`
**파일**: `projects/templates/projects/partials/project_timeline.html`
**작업**:
- ActionItem 시계열 (최신순)
- 각 이벤트:
  ```html
  <div class="border-l-2 border-slate-700 pl-4 py-2">
    <p class="text-xs text-slate-500">{{ action.created_at|date:"Y-m-d H:i" }}</p>
    <p class="text-sm text-slate-200">
      {{ action.action_type.label_ko }} · {{ action.application.candidate.name }}
    </p>
    {% if action.result %}
      <p class="text-xs text-slate-400 mt-1">{{ action.result }}</p>
    {% endif %}
  </div>
  ```

---

### T4b.9 — `partials/application_actions_list.html`
**파일**: `projects/templates/projects/partials/application_actions_list.html`
**작업**:
- 단순히 `application.action_items.all()`을 순회해서 `action_item_card.html` include
- HTMX swap target

---

### T4b.10 — `partials/project_applications_list.html`
**파일**: `projects/templates/projects/partials/project_applications_list.html`
**작업**:
- 프로젝트의 Application 목록을 partial로 분리
- HTMX swap target (필터 변경 시 부분 갱신)

---

### T4b.11 — `partials/view_filters.html` 재작성
**파일**: `projects/templates/projects/partials/view_filters.html`
**작업**:
- 기존 파일 백업 후 덮어쓰기
- phase select: 전체 / 서칭 / 심사 / 종료
- 담당자 select: 본인 / 전체 / 특정 컨설턴트
- 고객사 input (autocomplete)
- 마감 임박 체크박스
- HTMX `hx-get="{% url 'projects:project_list' %}"` + `hx-target` 또는 form submit

---

### T4b.12 — `candidates/candidate_detail.html` Application 섹션 추가
**파일**: `candidates/templates/candidates/candidate_detail.html`
**작업**: 기존 candidate_detail 페이지 하단에 Application 목록 섹션 추가.

```html
<!-- 기존 candidate detail 본문 위 또는 아래 -->
<section class="mt-8 rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
  <h2 class="mb-4 text-lg font-semibold">이 후보자의 모든 Application ({{ candidate.applications.count }})</h2>
  <div class="space-y-3">
    {% for app in candidate.applications.all %}
      <div class="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
        <a href="{% url 'projects:project_detail' app.project.id %}"
           class="text-sm font-semibold text-slate-100 hover:text-teal-300">
          {{ app.project.client.name }} · {{ app.project.title }}
        </a>
        <p class="mt-1 text-xs text-slate-400">
          상태: {{ app.current_state }}
          {% if app.dropped_at %}
            · 드롭 ({{ app.get_drop_reason_display }})
          {% elif app.hired_at %}
            · 입사 확정
          {% endif %}
        </p>
      </div>
    {% empty %}
      <p class="text-sm text-slate-500">아직 매칭된 프로젝트가 없습니다.</p>
    {% endfor %}
  </div>
</section>
```

**view 수정**: candidates/views.py의 candidate_detail이 `select_related("applications__project__client")` 또는 `prefetch_related`를 추가해야 N+1 회피.

---

### T4b.13 — `base.html`에 modal-container 추가
**파일**: `templates/base.html` (또는 유사 경로)
**작업**:
```html
<body>
  <!-- 기존 본문 -->
  {% block content %}{% endblock %}

  <div id="modal-container"></div>

  <!-- 기존 script -->
</body>
```

이미 있다면 스킵.

---

### T4b.14 — 레거시 템플릿 삭제
**작업**:
```bash
ls projects/templates/projects/partials/ | grep -E "tab_offers|dash_full|dash_pipeline|view_board_card"
```

발견된 파일 삭제:
```bash
rm projects/templates/projects/partials/tab_offers.html
rm projects/templates/projects/partials/dash_full.html
rm projects/templates/projects/partials/dash_pipeline.html
rm projects/templates/projects/partials/view_board_card.html
```

상위 템플릿에서 `{% include "...tab_offers..." %}` 같은 참조가 있으면 같이 제거.

추가 grep:
```bash
grep -rn "tab_offers\|dash_full\|dash_pipeline\|view_board_card" projects/templates/
```

---

### T4b.15 — `kanban.js` 정리
**파일**: `projects/static/js/kanban.js`
**작업**:
- 새 칸반에 드래그 앤 드롭 없음
- 파일 삭제 또는 빈 파일로 둠
- base.html / project_list.html에서 `<script src="...kanban.js">` 참조 제거

```bash
rm projects/static/js/kanban.js  # 또는 빈 파일로
grep -rn "kanban.js" projects/templates/ templates/
```

---

### T4b.16 — `manage.py check` + 전체 수동 확인
**작업**:
```bash
uv run python manage.py check
uv run python manage.py runserver 0.0.0.0:8000
```

**브라우저 확인 시나리오**:
1. `/dashboard/` 접근 → 대시보드 OK
2. `/projects/` → 칸반 OK, 필터 바 표시
3. 새 프로젝트 생성 → 상세 페이지로 이동
4. "후보자 추가" 버튼 클릭 → 모달 열림
5. 후보자 선택 → 추가 → Application 카드 표시
6. "+ 액션" 버튼 → 모달 → reach_out 선택 → 생성
7. ActionItem 카드의 [완료] 버튼 → 완료 모달 → result 입력 → 제출 → 후속 제안 모달
8. 후속 제안에서 schedule_pre_meet 선택 → 생성 → 새 ActionItem 표시
9. Application 드롭 → 드롭 모달 → 사유 선택 → 드롭 표시
10. 프로젝트 종료 → 종료 모달 → success 선택 → 종료 표시
11. 후보자 상세 페이지(`/candidates/<id>/`) → Application 섹션 표시

---

### T4b.17 — 잔여 grep
**작업**:
```bash
grep -rn "ProjectStatus\|Contact\|Offer" projects/templates/
```
→ 결과 0건.

---

## 5. 검증 체크리스트

- [ ] add_candidate, action_create, action_complete, action_propose_next, drop_application, project_close 모달 6개 작성
- [ ] project_timeline, application_actions_list, project_applications_list partial 작성
- [ ] view_filters 재작성 (phase 필터)
- [ ] candidates/candidate_detail.html Application 섹션 추가
- [ ] base.html에 #modal-container 존재
- [ ] tab_offers, dash_full, dash_pipeline, view_board_card 템플릿 삭제
- [ ] kanban.js 제거
- [ ] `grep ProjectStatus projects/templates/` → 0건
- [ ] 브라우저 전체 시나리오 통과

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| 모달 swap 후 카드 갱신이 비동기적으로 어긋남 | HTMX OOB(out-of-band) swap 또는 `hx-swap-oob` 사용. 또는 페이지 redirect로 단순화 |
| 후보자 검색 select가 너무 많은 옵션 (DB 후보자 수천 명) | Django select widget 대신 autocomplete 위젯 또는 ajax 검색. v1은 ModelChoiceField + select 기본 위젯으로 시작 |
| candidate_detail.html 기존 디자인이 다른 톤 | 일관성 위해 다크 네이비로 통일하되, 기존 페이지 전체 재작성은 범위 밖. 새 섹션만 일관 |
| 필터 변경 시 URL 업데이트 안 됨 | HTMX `hx-push-url="true"` 사용 |
| 레거시 템플릿 삭제로 다른 페이지 깨짐 | grep으로 모든 참조 확인 후 함께 정리 |

## 7. 커밋 포인트

```
feat(projects): add modals, filters, timeline, candidate detail section

- Add modal partials: add_candidate, action_create/complete/propose_next,
  drop_application, project_close
- Add project_timeline, application_actions_list, project_applications_list partials
- Rewrite view_filters with phase filter
- Add candidate detail Application list section
- Ensure base.html has #modal-container
- Remove legacy templates: tab_offers, dash_full, dash_pipeline, view_board_card
- Remove kanban.js (no drag-drop in 2-phase model)

Refs: FINAL-SPEC.md §5
```

## 8. Phase 5로 넘기는 인터페이스

- 모든 UI 플로우가 브라우저에서 동작
- HTMX 인터랙션 안정화
- Phase 5는 이 UI 위에서 단위 테스트와 통합 테스트를 작성

---

**이전 Phase**: [phase-4a-templates-core.md](phase-4a-templates-core.md)
**다음 Phase**: [phase-5-tests.md](phase-5-tests.md)
