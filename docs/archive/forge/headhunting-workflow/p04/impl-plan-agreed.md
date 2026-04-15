# P04: Project Multi-View — 확정 구현계획서

> **Phase:** 4
> **선행조건:** P03 (project list 존재)
> **산출물:** 보드(칸반), 리스트(액션), 테이블(스프레드시트) — 3가지 뷰 전환
> **캘린더 뷰는 v1에서 제외** (P05 이후 Event 데이터 충분 시 추가)

---

## 목표

프로젝트 목록을 3가지 뷰로 전환 가능하게 한다.
모든 뷰는 동일한 필터를 공유하며, 뷰 탭 전환만으로 관점을 바꾼다.

---

## 사전 작업

### tailwind.config.js 수정

```js
content: [
  './templates/**/*.html',
  './accounts/templates/**/*.html',
  './candidates/templates/**/*.html',
  './candidates/static/**/*.js',
  './clients/templates/**/*.html',     // 추가
  './projects/templates/**/*.html',    // 추가
  './projects/static/**/*.js',         // 추가
]
```

### Sortable.js CDN 추가

보드 뷰 템플릿의 script 블록에서 CDN 로드:
```html
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
```

---

## URL 설계

기존 `/projects/` URL에 `view` 파라미터 추가. 별도 URL 불필요.

| URL | 파라미터 | 설명 |
|-----|---------|------|
| `/projects/?view=board` | view=board | 칸반 보드 (기본값) |
| `/projects/?view=list` | view=list | 액션 중심 리스트 |
| `/projects/?view=table` | view=table | 스프레드시트 |

### 추가 URL

| URL | Method | 설명 |
|-----|--------|------|
| `/projects/<uuid:pk>/status/` | PATCH | 칸반 드래그앤드롭 상태 변경 |

필터 파라미터(`scope`, `client`, `status`, `sort`)는 뷰 전환 시 유지.

---

## View 변경

### project_list 확장

```python
@login_required
def project_list(request):
    org = _get_org(request)
    view_type = request.GET.get("view", "board")
    
    # 공통 필터/queryset (기존 scope/client/status/sort 로직 유지)
    projects = Project.objects.filter(organization=org)
    # scope, client, status 필터링...
    
    # 뷰별 context 준비
    if view_type == "board":
        # 전체 queryset (페이지네이션 OFF)
        # 상태별 그룹핑
        status_groups = {}
        for status_value, status_label in ProjectStatus.choices:
            status_groups[status_value] = {
                "label": status_label,
                "projects": projects.filter(status=status_value),
            }
        context["status_groups"] = status_groups
        
    elif view_type == "list":
        # 전체 queryset (페이지네이션 OFF)
        # 긴급도 기반 단순 분류 (days_elapsed 기준)
        red = projects.filter(created_at__lte=threshold_red)   # 경과일 상위
        yellow = projects.filter(...)   # 이번 주 면접 등
        green = projects.exclude(...)   # 나머지
        context["urgency_groups"] = [
            {"level": "red", "label": "긴급", "projects": red},
            {"level": "yellow", "label": "이번 주", "projects": yellow},
            {"level": "green", "label": "정상 진행", "projects": green},
        ]
        
    elif view_type == "table":
        # 페이지네이션 ON + annotate
        projects = projects.annotate(
            contact_count=Count("contacts"),
            submission_count=Count("submissions"),
            interview_count=Count("submissions__interviews"),
        )
        paginator = Paginator(projects, PAGE_SIZE)
        context["page_obj"] = paginator.get_page(request.GET.get("page"))
    
    template = f"projects/partials/view_{view_type}.html"
    
    # HTMX tab switch → partial만 반환
    if request.htmx and request.GET.get("tab_switch"):
        return render(request, template, context)
    
    # full page → project_list.html 렌더링 (탭 + 필터 + view content)
    context["view_template"] = template
    context["view_type"] = view_type
    return render(request, "projects/project_list.html", context)
```

### status_update (PATCH)

```python
@login_required
@require_http_methods(["PATCH"])
def status_update(request, pk):
    """칸반 드래그앤드롭 상태 변경."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    
    data = json.loads(request.body)
    new_status = data.get("status")
    
    if new_status not in ProjectStatus.values:
        return JsonResponse({"error": "invalid status"}, status=400)
    
    project.status = new_status
    project.save(update_fields=["status"])
    return HttpResponse(status=204)
```

---

## Template 구조

```
projects/templates/projects/
├── project_list.html              # full page (뷰 탭 + 필터 + #view-content)
└── partials/
    ├── view_tabs.html             # [보드] [리스트] [테이블] 탭
    ├── view_filters.html          # 공통 필터 바
    ├── view_board.html            # 칸반 보드
    ├── view_board_card.html       # 칸반 카드 단위
    ├── view_list.html             # 액션 중심 리스트
    └── view_table.html            # 스프레드시트
```

### project_list.html 구조

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}
{% block content %}
  <div>
    {% include "projects/partials/view_tabs.html" %}
    {% include "projects/partials/view_filters.html" %}
    <div id="view-content">
      {% include view_template %}
    </div>
  </div>
{% endblock %}
```

### 탭 전환 HTMX

```html
<!-- view_tabs.html -->
<a hx-get="/projects/?view=board&tab_switch=1&{{ existing_params }}" 
   hx-target="#view-content">
  보드
</a>
```

탭 전환: `hx-target="#view-content"` (뷰 영역만 교체)
전체 네비게이션: `hx-target="#main-content"` (기존 패턴)

---

## 보드 뷰 (칸반)

### 칼럼 구성 (전체 10 상태)

활성 칼럼: 신규, 서칭중, 추천진행, 면접진행, 오퍼협상
기타 칼럼: 보류, 승인대기
클로즈 칼럼: 성공/실패/취소 (기본 접힌 상태)

### 드래그앤드롭

```javascript
// static/js/kanban.js
new Sortable(column, {
    group: 'kanban',
    onEnd: function(evt) {
        const projectId = evt.item.dataset.projectId;
        const newStatus = evt.to.dataset.status;
        htmx.ajax('PATCH', `/projects/${projectId}/status/`, {
            headers: {'Content-Type': 'application/json'},
            values: JSON.stringify({status: newStatus}),
        });
    }
});
```

CSRF: `htmx.ajax()`는 body의 `hx-headers` 설정을 상속하므로 별도 처리 불필요.

---

## 리스트 뷰 (액션 중심)

### 긴급도 분류 (v1 단순화)

| 분류 | 조건 | 표시 |
|------|------|------|
| 🔴 긴급 | days_elapsed > 20 | 경과일 높은 프로젝트 |
| 🟡 이번 주 | days_elapsed 10~20 | 중간 경과 |
| 🟢 정상 | days_elapsed < 10 | 최근 등록 |

> 복잡한 긴급도 (미응답 컨택, 면접 임박 등)는 P13 대시보드에서 구현.

"다음 액션": ProjectContext.pending_action이 있으면 표시, 없으면 status 기반 기본 메시지.

---

## 테이블 뷰

컬럼: 고객사, 포지션, 상태, 담당, 컨택수, 추천수, 면접수, 경과일

```python
projects = projects.annotate(
    contact_count=Count("contacts"),
    submission_count=Count("submissions"),
    interview_count=Count("submissions__interviews"),
)
```

컬럼 헤더 클릭: `hx-get`로 sort 파라미터 변경 (서버 사이드 정렬).

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 뷰 전환 | 3개 탭 클릭 시 각각 다른 뷰 렌더링 |
| 필터 유지 | 뷰 전환 시 기존 필터 파라미터 보존 |
| 칸반 상태 변경 | PATCH /status/ → DB 반영 확인 |
| 테이블 annotate | 컨택/추천/면접 카운트 정확성 |
| 보드 전체 상태 | 10개 상태 모두 보드에 표시 |
| 페이지네이션 | 보드=전체, 테이블=페이지 |
| Organization 격리 | 타 조직 프로젝트 미표시 |

---

## 산출물

- `projects/views.py` — project_list 확장 + status_update
- `projects/urls.py` — status PATCH URL 추가
- `projects/templates/projects/partials/view_*.html` — 3개 뷰 + 탭 + 필터 + 카드
- `projects/templates/projects/project_list.html` — 뷰 탭 구조로 수정
- `static/js/kanban.js` — Sortable.js 드래그앤드롭
- `tailwind.config.js` — content 경로 추가
- 테스트 파일

<!-- forge:p04:구현담금질:complete:2026-04-08T15:00:00+09:00 -->
