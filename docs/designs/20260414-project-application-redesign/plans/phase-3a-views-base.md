# Phase 3a — Forms + URLs + 메인 뷰 레이어

**전제**: [Phase 2b](phase-2b-services-cleanup.md) 완료. 모든 서비스 함수가 새 모델 기반으로 동작.
**목표**: `forms.py` 전면 재작성, `urls.py`에 새 라우트 등록, `views.py`의 **메인 뷰**(대시보드, 2-phase 칸반, 프로젝트 상세, 프로젝트 생성/편집/종료/재오픈) 재작성.
**예상 시간**: 0.5-1일
**리스크**: 중 (기존 views.py 분석 범위 큼)
**범위**: Application CRUD, ActionItem CRUD, 레거시 offer/status_update/contact 제거는 [Phase 3b](phase-3b-views-crud.md)에서 처리.

---

## 1. 목표 상태

- `projects/forms.py` 전면 재작성 (`ProjectForm` 재작성, `OfferForm` 제거, `ApplicationCreateForm`·`ProjectCloseForm` 신규)
- `projects/urls.py`에 dashboard·project·application·action 라우트 등록 (action/application 뷰 본체는 Phase 3b에서 구현, 여기서는 path만 선언하거나 stub 뷰 연결)
- `projects/views.py`의 대시보드/칸반/프로젝트 상세 뷰 재작성
- `services/dashboard.py`의 함수들이 실제 뷰에서 호출됨
- `python manage.py check` + `manage.py runserver` 기동 시 dashboard·project 관련 URL이 응답 가능 (템플릿은 placeholder여도 무방)

## 2. 사전 조건

- Phase 2b 커밋 완료
- `services/dashboard.py`, `services/application_lifecycle.py`, `services/action_lifecycle.py`가 import 가능
- `signals.py`가 phase 재계산 + HIRED 자동 처리

## 3. 영향 범위

### 3.1 수정 파일
- `projects/forms.py` (522줄 → 재작성)
- `projects/urls.py` (341줄 → 새 라우트 추가, 구 라우트 일부 제거)
- `projects/views.py` (3,030줄 → **메인 뷰 섹션만** 재작성; 나머지는 Phase 3b)

### 3.2 신규 파일
- 없음 (모두 기존 파일 수정)

### 3.3 Phase 3b로 이월
- `views.py`의 Application·ActionItem CRUD 함수 (`application_drop`, `action_complete` 등)
- `views_voice.py` 수정
- 기존 오퍼·status_update·contact 뷰 제거

## 4. 태스크 분할

### T3a.1 — views.py 인벤토리 + 분할 지도
**작업**:
```bash
grep -n "^def \|^class " projects/views.py > /tmp/views_inventory.txt
wc -l projects/views.py
```

**산출물**: 각 뷰 함수를 카테고리로 분류.

| 카테고리 | 예시 함수 | Phase |
|---|---|---|
| 대시보드 (신규) | `dashboard`, `dashboard_todo_partial` | 3a |
| 프로젝트 칸반·상세 | `project_list`, `project_detail`, `project_create`, `project_edit`, `project_close`, `project_reopen`, `project_timeline_partial` | 3a |
| JD 관련 (유지) | `jd_upload`, `jd_edit`, Gemini 분석 등 | 유지 (수정 없음) |
| 승인 관련 (유지) | `approval_request`, `approval_approve` 등 | 유지 |
| 검색·매칭 (유지) | `search_candidates`, `match_candidates` 등 | 유지 |
| **Application CRUD** | `application_drop`, `application_restore`, `application_hire`, `project_add_candidate` | **3b** |
| **ActionItem CRUD** | `action_create`, `action_complete`, `action_skip`, `action_reschedule`, `action_propose_next` | **3b** |
| **레거시 제거 대상** | `offer_*`, `status_update`, `contact_*` | **3b** |

---

### T3a.2 — `forms.py` 전면 재작성
**파일**: `projects/forms.py`
**작업**: 기존 `OfferForm`, `ProjectStatusForm`, `SubmissionStatusForm`, Contact 관련 폼 전부 제거. 새 폼 추가.

```python
from django import forms

from projects.models import (
    Application,
    DropReason,
    Project,
    ProjectResult,
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "client",
            "title",
            "jd_text",
            "jd_file",
            "jd_source",
            "jd_drive_file_id",
            "requirements",
            "posting_text",
            "posting_file_name",
            "deadline",
            "assigned_consultants",
            "note",
        ]
        widgets = {
            "jd_text": forms.Textarea(attrs={"rows": 8}),
            "posting_text": forms.Textarea(attrs={"rows": 4}),
            "note": forms.Textarea(attrs={"rows": 3}),
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "requirements": forms.Textarea(attrs={"rows": 3}),
        }


class ApplicationCreateForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["candidate", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class ApplicationDropForm(forms.Form):
    drop_reason = forms.ChoiceField(choices=DropReason.choices, label="드롭 사유")
    drop_note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="메모",
    )


class ProjectCloseForm(forms.Form):
    result = forms.ChoiceField(choices=ProjectResult.choices, label="결과")
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        label="사유·메모",
    )


class ActionItemCreateForm(forms.Form):
    """
    view에서 action_type_id를 받아 ActionType instance로 변환 후 service 호출.
    폼은 가벼운 유효성만 담당.
    """
    action_type_id = forms.UUIDField()
    title = forms.CharField(max_length=300, required=False)
    channel = forms.CharField(max_length=20, required=False)
    scheduled_at = forms.DateTimeField(required=False)
    due_at = forms.DateTimeField(required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)


class ActionItemCompleteForm(forms.Form):
    result = forms.CharField(widget=forms.Textarea, required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)
    next_action_type_ids = forms.CharField(required=False)  # comma-separated UUIDs


class ActionItemSkipForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea, required=False)


class ActionItemRescheduleForm(forms.Form):
    new_due_at = forms.DateTimeField(required=False)
    new_scheduled_at = forms.DateTimeField(required=False)
```

**제거된 폼** (파일에서 삭제):
- `OfferForm`, `OfferStatusForm`
- `ContactForm` (있다면)
- `SubmissionStatusForm`, `ProjectStatusForm`
- 기타 `ProjectStatus` 기반 폼

**검증**: `python -c "from projects.forms import ProjectForm, ApplicationCreateForm, ProjectCloseForm; print('OK')"` 통과.

---

### T3a.3 — `urls.py` 재작성
**파일**: `projects/urls.py`
**작업**: 
- 기존 파일을 읽어서 유지할 라우트와 삭제할 라우트 판별
- 새 라우트 추가

**삭제 대상**:
- `path("<uuid:pk>/status/", views.status_update, name="status_update")`
- `path("<uuid:pk>/offer/", views.offer_*, ...)` 계열 전체
- `path("contacts/...)` 직접 CRUD (있다면)

**추가 대상** (Phase 3a가 구현할 메인 뷰 + Phase 3b가 구현할 CRUD 뷰):

```python
from django.urls import path

from projects import views

app_name = "projects"

urlpatterns = [
    # Dashboard (Phase 3a)
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/todo/", views.dashboard_todo_partial, name="dashboard_todo"),

    # Project (Phase 3a)
    path("", views.project_list, name="project_list"),
    path("new/", views.project_create, name="project_create"),
    path("<uuid:pk>/", views.project_detail, name="project_detail"),
    path("<uuid:pk>/edit/", views.project_edit, name="project_edit"),
    path("<uuid:pk>/close/", views.project_close, name="project_close"),
    path("<uuid:pk>/reopen/", views.project_reopen, name="project_reopen"),
    path("<uuid:pk>/applications/", views.project_applications_partial, name="project_applications"),
    path("<uuid:pk>/timeline/", views.project_timeline_partial, name="project_timeline"),

    # Application (Phase 3b; 여기서는 path만 선언 + stub view)
    path("<uuid:pk>/add_candidate/", views.project_add_candidate, name="project_add_candidate"),
    path("applications/<uuid:pk>/drop/", views.application_drop, name="application_drop"),
    path("applications/<uuid:pk>/restore/", views.application_restore, name="application_restore"),
    path("applications/<uuid:pk>/hire/", views.application_hire, name="application_hire"),

    # ActionItem (Phase 3b; 여기서는 path만 선언 + stub view)
    path("applications/<uuid:pk>/actions/", views.application_actions_partial, name="application_actions"),
    path("applications/<uuid:pk>/actions/new/", views.action_create, name="action_create"),
    path("actions/<uuid:pk>/complete/", views.action_complete, name="action_complete"),
    path("actions/<uuid:pk>/skip/", views.action_skip, name="action_skip"),
    path("actions/<uuid:pk>/reschedule/", views.action_reschedule, name="action_reschedule"),
    path("actions/<uuid:pk>/propose_next/", views.action_propose_next, name="action_propose_next"),

    # JD/Posting/Search/Approval (기존 유지)
    # ... (기존 라우트 복사)
]
```

**Phase 3b 대상 뷰의 stub**: Phase 3a 종료 시점에서는 `application_drop` 등의 함수가 `views.py`에 **최소 stub**으로 존재해야 `urls.py` import가 성공. stub은 아래 T3a.4에서 추가.

**검증**:
```bash
uv run python manage.py show_urls | grep -E "projects|dashboard"
```

---

### T3a.4 — `views.py` 섹션 분할 + stub 추가
**파일**: `projects/views.py`
**작업**: 
1. views.py 맨 위에 import 섹션 정리 (Phase 2b에서 제거된 lifecycle import 삭제)
2. 기존 코드 전체를 3개 섹션으로 논리 분할:
   - `# === Phase 3a: Dashboard + Project views ===`
   - `# === Phase 3b: Application + ActionItem views ===`
   - `# === Legacy (유지) ===` (JD, Approval, Search 등)
3. Phase 3b 섹션에 stub 함수들 추가 (urls.py 로딩을 위해):

```python
# === Phase 3b stubs — 실제 구현은 Phase 3b에서 ===

from django.http import HttpResponseNotAllowed
from django.shortcuts import render


def project_add_candidate(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def application_drop(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def application_restore(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def application_hire(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def application_actions_partial(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def action_create(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def action_complete(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def action_skip(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def action_reschedule(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])


def action_propose_next(request, pk):
    return HttpResponseNotAllowed(["Phase 3b에서 구현 예정"])
```

**주의**: stub은 **POST 요청 시 405 반환**만 하면 되므로 `HttpResponseNotAllowed` 또는 간단한 placeholder로 충분. Phase 3b에서 본체로 교체됨.

---

### T3a.5 — `dashboard` 뷰 구현
**파일**: `projects/views.py`
**작업**:
```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from projects.services.dashboard import (
    get_today_actions,
    get_overdue_actions,
    get_upcoming_actions,
)


@login_required
def dashboard(request):
    user = request.user
    context = {
        "today_actions": get_today_actions(user),
        "overdue_actions": get_overdue_actions(user),
        "upcoming_actions": get_upcoming_actions(user, days=3),
    }
    return render(request, "projects/dashboard/index.html", context)


@login_required
def dashboard_todo_partial(request):
    """HTMX partial, 오늘 할 일 리스트만 반환."""
    scope = request.GET.get("scope", "today")
    user = request.user
    if scope == "overdue":
        actions = get_overdue_actions(user)
    elif scope == "upcoming":
        actions = get_upcoming_actions(user)
    else:
        actions = get_today_actions(user)
    return render(
        request,
        "projects/partials/dashboard_todo_list.html",
        {"actions": actions, "scope": scope},
    )
```

**템플릿 placeholder**: Phase 4a에서 구현될 `dashboard/index.html`과 `partials/dashboard_todo_list.html`이 아직 없으므로, 최소 placeholder만 생성:

```bash
mkdir -p projects/templates/projects/dashboard
cat > projects/templates/projects/dashboard/index.html <<'EOF'
<h1>Dashboard (Phase 4a에서 구현)</h1>
<p>Today: {{ today_actions|length }}</p>
<p>Overdue: {{ overdue_actions|length }}</p>
<p>Upcoming: {{ upcoming_actions|length }}</p>
EOF
```

---

### T3a.6 — `project_list` 칸반 뷰 재작성
**파일**: `projects/views.py`
**작업**:
```python
from projects.services.dashboard import get_project_kanban_cards


@login_required
def project_list(request):
    organization = request.user.organization
    cards = get_project_kanban_cards(organization)
    # 필터 쿼리 파라미터 적용
    phase_filter = request.GET.get("phase")
    consultant_filter = request.GET.get("consultant")
    client_filter = request.GET.get("client")
    # ... (필터링 로직)
    context = {
        "kanban": cards,
        "phase_filter": phase_filter,
        "consultant_filter": consultant_filter,
        "client_filter": client_filter,
    }
    return render(request, "projects/project_list.html", context)
```

**드래그 앤 드롭**: 없음. `project_list.html`의 기존 JS 참조(`kanban.js`)는 Phase 4a에서 제거.

**기존 `project_list` 구현체를 덮어쓰기**. 기존 코드는 `ProjectStatus` 기반 필터링이므로 전체 교체.

---

### T3a.7 — `project_detail` 뷰 재작성
**파일**: `projects/views.py`
**작업**:
```python
from django.shortcuts import get_object_or_404

from projects.models import Application, ActionItem, ActionItemStatus, Project


@login_required
def project_detail(request, pk):
    project = get_object_or_404(
        Project,
        pk=pk,
        organization=request.user.organization,
    )
    applications = (
        Application.objects.filter(project=project)
        .select_related("candidate")
        .prefetch_related("action_items__action_type")
        .order_by("dropped_at", "-created_at")  # 활성 우선, 드롭은 하단
    )
    context = {
        "project": project,
        "applications": applications,
    }
    return render(request, "projects/project_detail.html", context)


@login_required
def project_applications_partial(request, pk):
    project = get_object_or_404(Project, pk=pk, organization=request.user.organization)
    applications = Application.objects.filter(project=project).select_related("candidate")
    return render(
        request,
        "projects/partials/project_applications_list.html",
        {"project": project, "applications": applications},
    )


@login_required
def project_timeline_partial(request, pk):
    project = get_object_or_404(Project, pk=pk, organization=request.user.organization)
    actions = (
        ActionItem.objects.filter(application__project=project)
        .select_related("application__candidate", "action_type", "assigned_to")
        .order_by("-created_at")[:100]
    )
    return render(
        request,
        "projects/partials/project_timeline.html",
        {"project": project, "actions": actions},
    )
```

---

### T3a.8 — `project_create` / `project_edit` 재작성
**파일**: `projects/views.py`
**작업**:
```python
from django.shortcuts import redirect

from projects.forms import ProjectForm


@login_required
def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES)
        if form.is_valid():
            project = form.save(commit=False)
            project.organization = request.user.organization
            project.created_by = request.user
            project.save()
            form.save_m2m()  # assigned_consultants
            return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm()
    return render(request, "projects/project_form.html", {"form": form, "mode": "create"})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk, organization=request.user.organization)
    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            form.save()
            return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, "projects/project_form.html", {"form": form, "mode": "edit"})
```

**기존 `project_create`/`project_edit`이 있으면 대체**. 기존이 ProjectStatus 필드를 세팅하고 있다면 제거.

---

### T3a.9 — `project_close` / `project_reopen` 구현
**파일**: `projects/views.py`
**작업**:
```python
from django.utils import timezone

from projects.forms import ProjectCloseForm


@login_required
def project_close(request, pk):
    project = get_object_or_404(Project, pk=pk, organization=request.user.organization)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = ProjectCloseForm(request.POST)
    if not form.is_valid():
        return render(request, "projects/partials/project_close_modal.html", {"form": form, "project": project})
    project.closed_at = timezone.now()
    project.result = form.cleaned_data["result"]
    project.note = form.cleaned_data["note"]
    project.save(update_fields=["closed_at", "result", "note", "updated_at"])
    return redirect("projects:project_detail", pk=project.pk)


@login_required
def project_reopen(request, pk):
    project = get_object_or_404(Project, pk=pk, organization=request.user.organization)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    project.closed_at = None
    project.result = ""
    project.save(update_fields=["closed_at", "result", "updated_at"])
    # signal이 status=open으로 자동 동기화
    return redirect("projects:project_detail", pk=project.pk)
```

---

### T3a.10 — `views.py`의 `ProjectStatus` 잔여 참조 확인
**작업**:
```bash
grep -n "ProjectStatus\|lifecycle\|Contact\|Offer" projects/views.py
```

Phase 3a 대상 메인 뷰에서는 전부 제거. Phase 3b 대상 코드(offer_*, status_update 등)는 그대로 남아있어도 무방 (Phase 3b에서 삭제).

단 `views.py` import 섹션에서 `from projects.services.lifecycle import ...` 같은 import가 있으면 **이 Phase에서 반드시 제거**. 남아있으면 ImportError로 서버가 뜨지 않음.

---

### T3a.11 — `manage.py check` + `runserver` 스모크 확인
**작업**:
```bash
uv run python manage.py check
```

**예상**:
- 에러 0건 (views 레이어까지)
- 단 `forms.py`, `views.py` 잔여 레거시 경고는 무시 가능 (Phase 3b에서 정리)

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

**수동 확인**:
- `http://localhost:8000/dashboard/` → 200, placeholder 렌더
- `http://localhost:8000/projects/` → 200, 빈 칸반
- 관리자 페이지 접근 가능

---

## 5. 검증 체크리스트

- [ ] `forms.py`에 새 폼 존재, 기존 OfferForm·ProjectStatusForm 제거
- [ ] `urls.py`에 dashboard/project/application/action 라우트 등록
- [ ] `views.py`의 dashboard, project_list, project_detail, project_create, project_edit, project_close, project_reopen 재작성 완료
- [ ] Phase 3b 대상 뷰가 stub으로 존재 (urls.py import 성공)
- [ ] `views.py`에서 `from projects.services.lifecycle import` 제거
- [ ] `python manage.py check` 통과
- [ ] `runserver` 기동 성공
- [ ] `/dashboard/`, `/projects/`, `/projects/new/` URL 200 응답 (placeholder 템플릿)
- [ ] `python manage.py show_urls | grep projects` → 새 라우트 전부 표시

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `views.py`가 3,030줄이라 단일 세션에서 전체 파악 어려움 | T3a.1 인벤토리로 분할 지도 확보. 실제 수정은 섹션별로 순차 편집 |
| 기존 `project_list` 등 뷰의 context가 템플릿과 dataset shape 달라서 깨짐 | Phase 4a 이전에는 placeholder 템플릿만 쓰므로 context만 맞으면 OK |
| stub 함수 signature 불일치로 urls.py 로딩 실패 | 모든 stub에 `(request, pk)` signature 통일 + `HttpResponseNotAllowed` 반환 |
| `ProjectForm`의 `assigned_consultants` M2M 저장 시점 | `form.save(commit=False)` 후 직접 필드 세팅 → `project.save()` → `form.save_m2m()` |
| 기존 `urls.py`의 유지 대상 라우트 누락 | grep으로 기존 라우트 전체 리스트 확보 후 새 파일에 복사 |
| `views.py`의 기존 JD/Approval/Search 뷰에도 간접적으로 lifecycle 호출이 있을 수 있음 | grep으로 발견 시 해당 호출 제거, 로직이 필요하면 새 서비스로 치환 |

## 7. 커밋 포인트

```
feat(projects): rewrite forms + urls + main views (dashboard/kanban/detail)

- Rewrite forms.py: new ProjectForm, ApplicationCreateForm, ProjectCloseForm,
  ActionItem* forms. Remove OfferForm/ProjectStatusForm/SubmissionStatusForm
- Rewrite urls.py: add dashboard/project/application/action routes,
  remove offer/status_update routes
- Rewrite views.py main section: dashboard, dashboard_todo_partial,
  project_list (2-phase kanban), project_detail, project_applications_partial,
  project_timeline_partial, project_create, project_edit, project_close, project_reopen
- Add stubs for Phase 3b views (application_*, action_*)

Refs: FINAL-SPEC.md §5
```

## 8. Phase 3b로 넘기는 인터페이스

- 메인 뷰가 동작
- Application·ActionItem 라우트는 URL에 등록됨, stub이 존재
- Phase 3b는 각 stub을 실제 구현으로 교체 + `project_add_candidate` 구현 + 레거시 제거

---

**이전 Phase**: [phase-2b-services-cleanup.md](phase-2b-services-cleanup.md)
**다음 Phase**: [phase-3b-views-crud.md](phase-3b-views-crud.md)
