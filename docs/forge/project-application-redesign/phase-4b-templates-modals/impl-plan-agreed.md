# Phase 4b — 모달 + 후보자 상세 + 필터바 + 레거시 정리 (확정본)

**전제**: [Phase 4a](phase-4a-templates-core.md) 완료. 메인 시각 구조와 카드가 동작.
**목표**: 모든 모달(액션 생성/완료/제안/건너뛰기/일정변경/드롭/프로젝트 종료/후보자 추가), 필터 바, 타임라인, 후보자 상세 Level 3 섹션을 구현. 레거시 템플릿 삭제.
**예상 시간**: 0.5-1일
**리스크**: 중

> **⚠️ 기존 디자인 스타일 유지, UI/UX 변경 최소화**: 현재 구현되어 있는 디자인 스타일을 변경하지 않는다. UI/UX도 데이터 모델 변경에 따라 불가피한 부분만 최소한으로 변경한다.

---

## 1. 목표 상태

- 모든 모달이 HTMX로 열리고 form submit 후 **엔드포인트별 응답 계약**에 따라 카드 swap + 모달 닫기가 동작
- `#modal-container`의 열기/닫기 라이프사이클이 명확히 정의됨
- `view_filters.html`이 **현재 백엔드가 지원하는** 필터 제공 (phase + status)
- `project_timeline.html`이 ActionItem 시계열 표시, 탭으로 접근 가능
- 후보자 상세 페이지(Level 3)에 해당 후보자의 모든 Application 섹션 추가 (**content partial 대상**)
- 레거시 템플릿 삭제
- `kanban.js` 제거 또는 비활성화
- 브라우저에서 전체 플로우 수동 확인

## 2. 사전 조건

- Phase 4a 커밋 완료
- 기존 디자인 스타일 확인 완료 (Phase 4a에서 기존 CSS 클래스 패턴 파악)
- `#modal-container`가 `templates/common/base.html`에 존재 (확인됨: line 77)

## 3. 영향 범위

### 3.1 신규 템플릿
- `projects/templates/projects/partials/add_candidate_modal.html`
- `projects/templates/projects/partials/action_create_modal.html`
- `projects/templates/projects/partials/action_complete_modal.html`
- `projects/templates/projects/partials/action_propose_next_modal.html`
- `projects/templates/projects/partials/action_skip_modal.html` ← **추가 (R1-08)**
- `projects/templates/projects/partials/action_reschedule_modal.html` ← **추가 (R1-08)**
- `projects/templates/projects/partials/drop_application_modal.html`
- `projects/templates/projects/partials/project_close_modal.html`
- `projects/templates/projects/partials/project_timeline.html`
- `projects/templates/projects/partials/application_actions_list.html`
- `projects/templates/projects/partials/project_applications_list.html`
- `projects/templates/projects/partials/view_filters.html` (재작성)

### 3.2 수정 템플릿
- `candidates/templates/candidates/partials/candidate_detail_content.html` ← **수정 (R1-06: content partial이 실제 대상)**
- `projects/templates/projects/project_detail.html` — 타임라인 탭 활성화 (R1-10)
- `templates/common/base.html` — `#modal-container` 클래스 조정 (R1-01)

### 3.3 수정 뷰
- `projects/views.py::project_close` — GET 핸들러 추가 (R1-03)
- `candidates/views.py::candidate_detail` — prefetch 추가 (R1-07)
- Partial 뷰 응답의 prefetch 계약 명시 (R1-11)

### 3.4 삭제 템플릿
- `projects/templates/projects/partials/tab_offers.html`
- `projects/templates/projects/partials/dash_full.html`
- `projects/templates/projects/partials/dash_pipeline.html`
- `projects/templates/projects/partials/view_board_card.html`
- 기타 참조가 없는 레거시 partial (grep으로 확인)

### 3.5 정적 자산 정리
- `projects/static/js/kanban.js` 삭제 또는 비우기

## 4. 모달 공용 컨벤션 (R1-01, R1-09 반영)

### 4.1 `#modal-container` 라이프사이클

현재 `templates/common/base.html`:
```html
<div id="modal-container" class="fixed inset-0 z-50 hidden"></div>
```

**열기 규칙**: HTMX가 `innerHTML`을 swap하면 JS로 `hidden` 클래스를 제거.
**닫기 규칙**: `hidden` 복구 + `innerHTML` 비우기.

**구현**: `base.html`의 `#modal-container`에 HTMX 이벤트 리스너 추가:

```html
<div id="modal-container"
     class="fixed inset-0 z-50 hidden"
     hx-on::after-swap="this.classList.remove('hidden')"
     ></div>
```

닫기 함수 (전역):
```javascript
function closeModal() {
  const mc = document.getElementById('modal-container');
  mc.innerHTML = '';
  mc.classList.add('hidden');
}
```

### 4.2 모달 partial 공통 구조 (R1-09 접근성 반영)

```html
<!-- #modal-container 안에 swap되는 내용 -->
<div class="flex items-center justify-center min-h-full p-4"
     onclick="if (event.target === this) closeModal()">
  <div role="dialog"
       aria-modal="true"
       aria-labelledby="modal-title"
       class="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl"
       @keydown.escape.window="closeModal()">
    <header class="mb-4 flex items-center justify-between">
      <h2 id="modal-title" class="text-lg font-semibold text-slate-100">{{ modal_title }}</h2>
      <button onclick="closeModal()" type="button"
              class="text-slate-500 hover:text-slate-300" aria-label="닫기">✕</button>
    </header>
    <!-- 모달 내용 -->
  </div>
</div>
```

**NOT included (v2)**: focus trap, background `inert`.

### 4.3 z-index 분리

모달은 `z-50`(기존), 토스트는 `z-[60]` 이상으로 분리하여 토스트가 항상 모달 위에 표시되도록 한다. `templates/common/base.html`의 `#toast-container` 수정.

## 5. 엔드포인트별 응답 계약 (R1-02 반영)

각 모달 form의 POST 성공 시 서버 응답과 클라이언트 처리를 명확히 정의한다.

| 엔드포인트 | POST 성공 응답 | 모달 닫기 방식 | 목록 갱신 방식 |
|---|---|---|---|
| `project_add_candidate` | `204 + HX-Trigger("applicationChanged")` | `hx-on::after-request="if(event.detail.successful) closeModal()"` | `applicationChanged` 이벤트가 `#project-applications-container` 갱신 |
| `application_drop` | rendered `application_card.html` + `HX-Trigger("applicationChanged")` | 서버가 카드를 반환하므로 모달에 카드가 들어감 → **변경 필요**: `204 + HX-Trigger`로 통일 | `applicationChanged` 이벤트 |
| `action_create` | `204 + HX-Trigger("actionChanged")` | `hx-on::after-request` | `actionChanged` 이벤트 |
| `action_complete` | (후속 있으면) rendered `action_propose_next_modal` + `HX-Trigger("actionChanged")` / (없으면) `204 + HX-Trigger` | 후속 모달이 `#modal-container`에 swap됨 (모달→모달 전환) / 없으면 `closeModal()` | `actionChanged` 이벤트 |
| `action_propose_next` | `204 + HX-Trigger("actionChanged")` | `hx-on::after-request` | `actionChanged` 이벤트 |
| `action_skip` | `204 + HX-Trigger("actionChanged")` | `hx-on::after-request` | `actionChanged` 이벤트 |
| `action_reschedule` | `204 + HX-Trigger("actionChanged")` | `hx-on::after-request` | `actionChanged` 이벤트 |
| `project_close` | `204 + HX-Trigger("projectChanged")` 또는 redirect → **변경 필요**: HTMX 요청 시 `HX-Redirect` 헤더 사용 | 모달 닫기 + 페이지 이동 | 상세 페이지 리로드 |

**`application_drop` 뷰 수정** (R1-02): 현재 `application_card.html`을 반환하는데, 이를 `204 + HX-Trigger("applicationChanged")`로 변경하여 다른 엔드포인트와 통일한다. `applicationChanged` 이벤트가 이미 전체 목록을 갱신하므로 개별 카드 반환은 불필요하다.

**`project_close` 뷰 수정** (R1-03): GET+POST로 확장.
- GET: 모달 form 렌더링 (`ProjectCloseForm` + project context)
- POST (HTMX): `HX-Redirect` 헤더로 상세 페이지 이동
- POST (non-HTMX): 기존 redirect 유지

```python
# project_close 수정
@login_required
@membership_required
def project_close(request, pk):
    """GET: 종료 모달 렌더링. POST: 프로젝트 종료."""
    # (기존 permission 체크)
    if request.method == "GET":
        form = ProjectCloseForm()
        return render(request, "projects/partials/project_close_modal.html",
                      {"form": form, "project": project})
    # POST: 기존 로직 유지 + HTMX 분기
    # ...
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = reverse("projects:project_detail", args=[project.pk])
        return response
    return redirect("projects:project_detail", pk=project.pk)
```

## 6. 태스크 분할

### T4b.1 — `base.html` 모달 라이프사이클 설정

**파일**: `templates/common/base.html`
**작업**:
1. `#modal-container`에 `hx-on::after-swap="this.classList.remove('hidden')"` 추가
2. `closeModal()` JS 함수 추가 (전역)
3. `#toast-container`의 z-index를 `z-[60]`으로 상향

---

### T4b.2 — `partials/add_candidate_modal.html`

**파일**: `projects/templates/projects/partials/add_candidate_modal.html`
**구조**: §4.2 공용 구조 사용.

```html
<div class="flex items-center justify-center min-h-full p-4"
     onclick="if (event.target === this) closeModal()">
  <div role="dialog" aria-modal="true" aria-labelledby="modal-title"
       class="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900 p-6"
       @keydown.escape.window="closeModal()">
    <header class="mb-4 flex items-center justify-between">
      <h2 id="modal-title" class="text-lg font-semibold text-slate-100">후보자 추가</h2>
      <button onclick="closeModal()" type="button"
              class="text-slate-500 hover:text-slate-300" aria-label="닫기">✕</button>
    </header>

    <!-- 탭 -->
    <div class="mb-4 flex gap-1 border-b border-slate-800">
      <button type="button"
              class="border-b-2 border-teal-500 px-4 py-2 text-sm text-teal-300">
        DB 검색
      </button>
      <button type="button" class="px-4 py-2 text-sm text-slate-500" disabled>
        파일 업로드 (준비 중)
      </button>
      <button type="button" class="px-4 py-2 text-sm text-slate-500" disabled>
        Drive (준비 중)
      </button>
    </div>

    <form hx-post="{% url 'projects:project_add_candidate' project.id %}"
          hx-target="#modal-container"
          hx-swap="innerHTML"
          hx-on::after-request="if(event.detail.successful) closeModal()">
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
        <button type="button" onclick="closeModal()"
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

**참고**: 파일 업로드/Drive 탭은 v1에서 비활성. 향후 확장 자리만 마련.

---

### T4b.3 — `partials/action_create_modal.html`

**파일**: `projects/templates/projects/partials/action_create_modal.html`
**작업**: §4.2 공용 구조 사용.
- action_type select (active만, context에서 `action_types` 전달)
- title input (선택, 자동 생성 가능)
- channel select
- scheduled_at, due_at datetime-local
- note textarea
- `hx-post="{% url 'projects:action_create' application.id %}"`
- `hx-on::after-request="if(event.detail.successful) closeModal()"`

---

### T4b.4 — `partials/action_complete_modal.html` (R1-04 반영)

**파일**: `projects/templates/projects/partials/action_complete_modal.html`
**작업**: §4.2 공용 구조 사용.
- result textarea
- note textarea
- ~~next_action 체크박스 목록~~ **삭제** — 후속 액션 선택은 `action_propose_next_modal`에서만 수행
- `hx-post="{% url 'projects:action_complete' action.id %}"`
- `hx-target="#modal-container"` (후속 제안이 있으면 propose_next 모달이 swap됨)
- 후속 제안이 없으면 서버가 `204 + HX-Trigger` 반환 → `hx-on::after-request="if(event.detail.successful && event.detail.xhr.status===204) closeModal()"`

---

### T4b.5 — `partials/action_propose_next_modal.html`

**파일**: `projects/templates/projects/partials/action_propose_next_modal.html`
**작업**: §4.2 공용 구조 사용.
- 완료된 액션 정보 표시
- 제안된 ActionType 체크박스 목록 (`suggestions` context)
- 각 체크박스의 name은 `next_action_type_ids` (현재 뷰가 읽는 필드명)
- ~~각 체크박스 옆에 due_at 입력~~ **삭제** — 현재 백엔드가 소비하지 않음 (R1-04)
- `hx-post="{% url 'projects:action_propose_next' action.id %}"`
- `hx-on::after-request="if(event.detail.successful) closeModal()"`
- "건너뛰기" 버튼: `closeModal()` 호출

---

### T4b.6 — `partials/action_skip_modal.html` (R1-08 추가)

**파일**: `projects/templates/projects/partials/action_skip_modal.html`
**작업**: §4.2 공용 구조 사용.
- note textarea (건너뛰기 사유)
- `hx-post="{% url 'projects:action_skip' action.id %}"`
- `hx-on::after-request="if(event.detail.successful) closeModal()"`

---

### T4b.7 — `partials/action_reschedule_modal.html` (R1-08 추가)

**파일**: `projects/templates/projects/partials/action_reschedule_modal.html`
**작업**: §4.2 공용 구조 사용.
- scheduled_at datetime-local (새 일정)
- due_at datetime-local (새 마감)
- note textarea
- `hx-post="{% url 'projects:action_reschedule' action.id %}"`
- `hx-on::after-request="if(event.detail.successful) closeModal()"`

---

### T4b.8 — `partials/drop_application_modal.html`

**파일**: `projects/templates/projects/partials/drop_application_modal.html`
**작업**: §4.2 공용 구조 사용.
- drop_reason 라디오 (4개 enum: unfit/candidate_declined/client_rejected/other, label은 한국어)
- drop_note textarea
- `hx-post="{% url 'projects:application_drop' application.id %}"`
- `hx-on::after-request="if(event.detail.successful) closeModal()"`

---

### T4b.9 — `partials/project_close_modal.html` + 뷰 수정 (R1-03 반영)

**파일**: `projects/templates/projects/partials/project_close_modal.html`
**작업**: §4.2 공용 구조 사용.
- result 라디오 (success/fail)
- note textarea (필수)
- 활성 Application 수 경고 메시지 (있으면)
- `hx-post="{% url 'projects:project_close' project.id %}"`

**뷰 수정** (`projects/views.py::project_close`):
- `@require_http_methods(["POST"])` → `@require_http_methods(["GET", "POST"])` 변경
- GET: `ProjectCloseForm()` + project context 렌더링
- POST (HTMX): 기존 로직 + `HX-Redirect` 헤더로 상세 페이지 이동
- POST (non-HTMX): 기존 redirect 유지

---

### T4b.10 — `partials/project_timeline.html` + 탭 활성화 (R1-10, R1-12 반영)

**파일**: `projects/templates/projects/partials/project_timeline.html`
**작업**:
- ActionItem 시계열 (**`-created_at` 정렬**, R1-12)
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

**프로젝트 상세 수정** (`project_detail.html`, R1-10):
- 타임라인 탭의 `disabled` 속성 제거
- 탭 전환 JS 추가: 클릭 시 `hx-get="{% url 'projects:project_timeline' project.id %}"` → `#tab-content`에 swap
- Applications 탭도 `hx-get`으로 동적 로드 (또는 기존 inline 유지)

**뷰 확인**: `project_timeline_partial` 뷰(views.py:368)에 `select_related("action_type", "application__candidate")` 추가 (R1-11).

---

### T4b.11 — `partials/application_actions_list.html` (R1-11, R1-12 반영)

**파일**: `projects/templates/projects/partials/application_actions_list.html`
**작업**:
- `application`의 action_items를 순회하여 `action_item_card.html` include
- **정렬 명시**: 뷰에서 `application.action_items.select_related("action_type").order_by("status", "due_at", "created_at")` queryset을 context로 전달 (R1-12)
- HTMX swap target

---

### T4b.12 — `partials/project_applications_list.html` (R1-11 반영)

**파일**: `projects/templates/projects/partials/project_applications_list.html`
**작업**:
- 프로젝트의 Application 목록을 partial로 분리
- **뷰 prefetch 계약** (R1-11): `project_applications_partial` 뷰에서 `applications.select_related("candidate").prefetch_related(Prefetch("action_items", queryset=ActionItem.objects.select_related("action_type").order_by("status", "due_at", "created_at")))` 사용
- HTMX swap target (필터 변경 시 부분 갱신)

---

### T4b.13 — `partials/view_filters.html` 재작성 (R1-05 반영)

**파일**: `projects/templates/projects/partials/view_filters.html`
**작업**:
- 기존 파일 백업 후 덮어쓰기
- **phase select**: 전체 / 서칭 / 심사 ← **`종료` 제거** (종료는 status 필터로 분리)
- **status select**: 전체 / 진행중 / 종료 ← **추가** (R1-05: phase와 status 분리)
- 담당자 select: 본인 / 전체 / 특정 컨설턴트
- ~~고객사 input (autocomplete)~~ — 현재 백엔드 미지원, v2로 이동
- ~~마감 임박 체크박스~~ — 현재 백엔드 미지원, v2로 이동
- HTMX `hx-get` + `hx-target`

**뷰/서비스 수정** (R1-05): `project_list` 뷰 또는 `get_project_kanban_cards` 서비스에 `phase`, `status`, `consultant` 파라미터 필터링 로직 추가. 최소한의 변경:
```python
# project_list 뷰 내
phase = request.GET.get("phase")
status = request.GET.get("status")
consultant = request.GET.get("consultant")

qs = Project.objects.filter(organization=org)
if phase:
    qs = qs.filter(phase=phase)
if status:
    qs = qs.filter(status=status)
if consultant:
    qs = qs.filter(assigned_consultants__pk=consultant)
```

---

### T4b.14 — `candidate_detail_content.html` Application 섹션 추가 (R1-06, R1-07 반영)

**파일**: `candidates/templates/candidates/partials/candidate_detail_content.html` ← **수정 (R1-06)**
**작업**: 기존 content partial 하단에 Application 목록 섹션 추가.

```html
<section class="mt-8 rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
  <h2 class="mb-4 text-lg font-semibold">이 후보자의 모든 Application ({{ applications|length }})</h2>
  <div class="space-y-3">
    {% for app in applications %}
      <div class="rounded-xl border border-slate-800 bg-slate-900/80 p-4">
        <a href="{% url 'projects:project_detail' app.project.id %}"
           class="text-sm font-semibold text-slate-100 hover:text-teal-300">
          {{ app.project.client.name }} · {{ app.project.title }}
        </a>
        <p class="mt-1 text-xs text-slate-400">
          상태: {{ app.current_state_display }}
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

**뷰 수정** (`candidates/views.py::candidate_detail`, R1-07):
```python
from django.db.models import Prefetch
from projects.models import Application, ActionItem

applications = Application.objects.filter(
    candidate=candidate
).select_related(
    "project__client"
).prefetch_related(
    Prefetch(
        "action_items",
        queryset=ActionItem.objects.select_related("action_type").order_by("-completed_at"),
    )
)
```

**`current_state` N+1 대응** (R1-07): `current_state` property는 prefetched `action_items`를 이미 캐시하고 있으므로, `prefetch_related`로 `action_items`를 미리 로드하면 각 Application마다 추가 쿼리가 발생하지 않는다. Django의 prefetch는 `self.action_items.filter(...)` 호출 시 캐시를 사용한다.

단, `current_state`가 `filter(status=...)` 조건을 사용하므로 prefetch queryset에 동일 필터가 없으면 캐시 miss가 발생할 수 있다. 이 경우 별도 `Prefetch("action_items", queryset=..., to_attr="prefetched_done_actions")`를 사용하고 `current_state`를 뷰에서 계산하여 context에 넣는 방식으로 전환한다. 구현 시 실측하여 결정.

---

### T4b.15 — `application_drop` 뷰 수정 (R1-02 반영)

**파일**: `projects/views.py::application_drop`
**작업**: POST 성공 시 `application_card.html` 렌더링 대신 `204 + HX-Trigger("applicationChanged")`로 변경.

```python
# application_drop POST 성공 분기 수정
if request.headers.get("HX-Request"):
    response = HttpResponse(status=204)
    response["HX-Trigger"] = "applicationChanged"
    return response
return redirect("projects:project_detail", pk=application.project.pk)
```

---

### T4b.16 — 레거시 템플릿 삭제

**작업**:
```bash
# 삭제 대상 확인
grep -rn "tab_offers\|dash_full\|dash_pipeline\|view_board_card" projects/templates/
```

발견된 파일 삭제 + 참조 제거.

---

### T4b.17 — `kanban.js` 정리

**파일**: `projects/static/js/kanban.js`
**작업**:
- 파일 삭제
- `<script src="...kanban.js">` 참조 제거

```bash
grep -rn "kanban.js" projects/templates/ templates/
```

---

### T4b.18 — `manage.py check` + 전체 수동 확인

**작업**:
```bash
uv run python manage.py check
uv run pytest -v
uv run python manage.py runserver 0.0.0.0:8000
```

**브라우저 확인 시나리오**:
1. `/dashboard/` 접근 → 대시보드 OK
2. `/projects/` → 칸반 OK, 필터 바 표시 (phase/status/담당자 필터 동작 확인)
3. 새 프로젝트 생성 → 상세 페이지로 이동
4. "후보자 추가" 버튼 클릭 → 모달 열림 (hidden 제거 확인)
5. 후보자 선택 → 추가 → 모달 닫힘 + Application 카드 표시
6. "+ 액션" 버튼 → 모달 → reach_out 선택 → 생성 → 모달 닫힘
7. ActionItem 카드의 [완료] 버튼 → 완료 모달 → result 입력 → 제출 → 후속 제안 모달
8. 후속 제안에서 schedule_pre_meet 선택 → 생성 → 모달 닫힘 + 새 ActionItem 표시
9. ActionItem 카드의 [건너뛰기] 버튼 → 건너뛰기 모달 → 사유 입력 → 모달 닫힘
10. ActionItem 카드의 [나중에] 버튼 → 일정 변경 모달 → 새 일정 입력 → 모달 닫힘
11. Application 드롭 → 드롭 모달 → 사유 선택 → 모달 닫힘 + 드롭 표시
12. 타임라인 탭 클릭 → ActionItem 시계열 표시
13. 프로젝트 종료 → 종료 모달 (GET으로 열림) → success 선택 → 종료 표시
14. 후보자 상세 페이지(`/candidates/<id>/`) → Application 섹션 표시
15. Escape 키로 모달 닫기 확인

---

### T4b.19 — 잔여 grep (R1-13 반영)

**작업**:
```bash
# 실제 삭제 대상만 검색 (ProjectStatus는 유효한 현재 enum이므로 제외)
grep -rn "Contact\|Offer" projects/templates/ --include="*.html"
```
→ 결과 0건.

---

## 7. 검증 체크리스트

- [ ] add_candidate, action_create, action_complete, action_propose_next, **action_skip, action_reschedule**, drop_application, project_close 모달 **8개** 작성
- [ ] `#modal-container` 열기/닫기 라이프사이클 동작 (hidden 토글)
- [ ] 모달에 `role="dialog"`, `aria-modal`, `aria-labelledby`, `max-h-[90vh] overflow-y-auto`, Escape 닫기
- [ ] project_timeline, application_actions_list, project_applications_list partial 작성
- [ ] view_filters 재작성 (phase + **status** 분리 필터, 백엔드 연동)
- [ ] `candidate_detail_content.html` Application 섹션 추가 (content partial 대상)
- [ ] `candidate_detail` 뷰에 Prefetch 추가
- [ ] `project_close` 뷰 GET 핸들러 추가
- [ ] `application_drop` 뷰 응답을 204+HX-Trigger로 통일
- [ ] 타임라인 탭 활성화 + hx-get 연결
- [ ] tab_offers, dash_full, dash_pipeline, view_board_card 템플릿 삭제
- [ ] kanban.js 제거
- [ ] `grep Contact\|Offer projects/templates/` → 0건
- [ ] Partial 뷰 prefetch 계약 적용
- [ ] 브라우저 전체 시나리오 통과 (15개 항목)

## 8. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| 모달 swap 후 카드 갱신 비동기 불일치 | 엔드포인트별 응답 계약(§5)으로 통일. `hx-on::after-request`로 성공 시 닫기 |
| 후보자 검색 select가 너무 많은 옵션 | v1은 ModelChoiceField + select 기본 위젯. 향후 autocomplete |
| candidate_detail_content.html 기존 디자인과 톤 차이 | 기존 스타일 유지. 새 섹션은 동일 톤 사용 |
| 필터 변경 시 URL 미업데이트 | HTMX `hx-push-url="true"` 사용 |
| 레거시 템플릿 삭제로 다른 페이지 깨짐 | grep으로 모든 참조 확인 후 함께 정리 |
| current_state N+1 | Prefetch로 1차 대응, 실측 후 annotate 전환 검토 |

## 9. 커밋 포인트

```
feat(projects): add modals, filters, timeline, candidate detail section

- Add modal partials: add_candidate, action_create/complete/propose_next,
  action_skip, action_reschedule, drop_application, project_close (8 modals)
- Define #modal-container lifecycle (hidden toggle + closeModal())
- Add accessibility: role=dialog, aria-modal, overflow, Escape
- Add project_timeline, application_actions_list, project_applications_list
- Rewrite view_filters with phase + status filters (backend-integrated)
- Add candidate detail Application list section (content partial)
- Fix project_close view: add GET handler for modal form
- Unify application_drop response to 204+HX-Trigger
- Enable timeline tab in project_detail
- Add prefetch contracts to partial views
- Remove legacy: tab_offers, dash_full, dash_pipeline, view_board_card, kanban.js

Refs: FINAL-SPEC.md §5
```

## 10. Phase 5로 넘기는 인터페이스

- 모든 UI 플로우가 브라우저에서 동작 (모달 8개 + 필터 + 타임라인)
- HTMX 인터랙션 안정화 (엔드포인트별 응답 계약 적용)
- Phase 5는 이 UI 위에서 단위 테스트와 통합 테스트를 작성

---

**이전 Phase**: [phase-4a-templates-core](../phase-4a-templates-core/impl-plan-agreed.md)
**다음 Phase**: [phase-5-tests](../phase-5-tests/debate/impl-plan.md)

<!-- forge:phase-4b-templates-modals:impl-plan:complete:2026-04-14T21:00:00Z -->
