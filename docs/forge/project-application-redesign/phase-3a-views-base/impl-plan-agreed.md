# Phase 3a — Forms + URLs + 메인 뷰 레이어 (확정본)

**전제**: [Phase 2b](phase-2b-services-cleanup.md) 완료. 모든 서비스 함수가 새 모델 기반으로 동작.
**목표**: `forms.py`에 신규 폼 추가 (기존 폼 보존), `urls.py`에 새 라우트 등록, `views.py`의 **메인 뷰**(대시보드, 2-phase 칸반, 프로젝트 상세, 프로젝트 생성/편집/종료/재오픈) 재작성. `main/urls.py`에 대시보드 라우트 재연결.
**예상 시간**: 0.5-1일
**리스크**: 중 (기존 views.py 분석 범위 큼)
**범위**: Application CRUD, ActionItem CRUD, 레거시 offer/status_update/contact 제거는 [Phase 3b](phase-3b-views-crud.md)에서 처리.

---

## 핵심 원칙 (담금질 결과)

1. **모든 뷰에 `@membership_required` + `org = _get_org(request)` 패턴 적용.** `request.user.organization` 사용 금지 — 코드베이스에 존재하지 않는 속성.
2. **기존 폼/URL name/뷰 보존.** 새 코드는 추가만. 기존 것 삭제는 Phase 3b 이후.
3. **대시보드 URL은 `main/urls.py`에서 관리.** `projects/urls.py`에 dashboard 라우트 추가하지 않음.
4. **기존 비즈니스 워크플로 유지.** 충돌 감지, 승인, 역할 기반 스코핑 등 기존 로직 보존.
5. **기존 디자인 스타일/UI/UX 변경 최소화.** 데이터 모델 변경에 따라 불가피한 부분만 변경.

---

## 1. 목표 상태

- `projects/forms.py`에 신규 폼 추가 (`ApplicationCreateForm`, `ApplicationDropForm`, `ProjectCloseForm`, `ActionItem*Form`). **기존 폼(ProjectForm 포함) 보존** — Phase 3b에서 레거시 폼 정리
- `projects/urls.py`에 프로젝트·application·action 라우트 등록 (기존 라우트 유지, 새 라우트 추가). Phase 3b 뷰는 stub 연결
- `main/urls.py`에서 대시보드 뷰를 새 구현으로 교체
- `projects/views.py`의 대시보드/칸반/프로젝트 상세 뷰 재작성
- `services/dashboard.py`의 함수들이 실제 뷰에서 호출됨
- `python manage.py check` + `manage.py runserver` 기동 시 모든 URL이 응답 가능 (템플릿은 placeholder여도 무방)

## 2. 사전 조건

- Phase 2b 커밋 완료
- `services/dashboard.py`, `services/application_lifecycle.py`, `services/action_lifecycle.py`가 import 가능
- `signals.py`가 phase 재계산 + HIRED 자동 처리
- `accounts.decorators.membership_required`, `accounts.helpers._get_org` import 가능

## 3. 영향 범위

### 3.1 수정 파일
- `projects/forms.py` (522줄 → 신규 폼 추가, 기존 폼 보존)
- `projects/urls.py` (341줄 → 새 라우트 추가, 구 라우트 유지)
- `projects/views.py` (3,030줄 → 메인 뷰 섹션 재작성; 나머지 보존)
- `main/urls.py` — 대시보드 뷰 교체

### 3.2 신규 파일
- `projects/templates/projects/dashboard/index.html` (placeholder)
- `projects/templates/projects/partials/dashboard_todo_list.html` (placeholder)

### 3.3 Phase 3b로 이월
- `views.py`의 Application·ActionItem CRUD 함수
- `views_voice.py` 수정
- 기존 오퍼·status_update·contact 뷰 제거
- 기존 레거시 폼 제거 (OfferForm, ProjectStatusForm 등)

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
| 대시보드 (교체) | `dashboard`, `dashboard_todo_partial` | 3a (main/urls.py에서 교체) |
| 프로젝트 칸반·상세 | `project_list`, `project_detail`, `project_create`, `project_update`, `project_close`, `project_reopen`, `project_timeline_partial` | 3a |
| JD 관련 (유지) | `jd_upload`, `jd_edit`, Gemini 분석 등 | 유지 (수정 없음) |
| 승인 관련 (유지) | `approval_request`, `approval_approve` 등 | 유지 |
| 검색·매칭 (유지) | `search_candidates`, `match_candidates` 등 | 유지 |
| 충돌 감지 (유지) | `project_check_collision` | 유지 |
| **Application CRUD** | `application_drop`, `application_restore`, `application_hire`, `project_add_candidate` | **3b** |
| **ActionItem CRUD** | `action_create`, `action_complete`, `action_skip`, `action_reschedule`, `action_propose_next` | **3b** |
| **레거시 제거 대상** | `offer_*`, `status_update`, `contact_*` | **3b** |

---

### T3a.2 — `forms.py` 신규 폼 추가 (기존 보존)
**파일**: `projects/forms.py`
**작업**: **기존 폼을 모두 보존**한 채, 파일 끝에 신규 폼을 추가.

```python
# ========================================
# Phase 3a: 신규 폼 (기존 폼 아래에 추가)
# ========================================

from projects.models import (
    Application,
    DropReason,
    ProjectResult,
)


class ApplicationCreateForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["candidate", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            from candidates.models import Candidate
            self.fields["candidate"].queryset = Candidate.objects.filter(
                owned_by=organization
            )


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
    action_type_id = forms.UUIDField()
    title = forms.CharField(max_length=300, required=False)
    channel = forms.CharField(max_length=20, required=False)
    scheduled_at = forms.DateTimeField(required=False)
    due_at = forms.DateTimeField(required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)


class ActionItemCompleteForm(forms.Form):
    result = forms.CharField(widget=forms.Textarea, required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)
    next_action_type_ids = forms.CharField(required=False)


class ActionItemSkipForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea, required=False)


class ActionItemRescheduleForm(forms.Form):
    new_due_at = forms.DateTimeField(required=False)
    new_scheduled_at = forms.DateTimeField(required=False)
```

**기존 ProjectForm은 수정하지 않음.** org-scoped queryset이 이미 존재함 (현 `__init__`의 `organization=` 인자).

**검증**: `python -c "from projects.forms import ProjectForm, ApplicationCreateForm, ProjectCloseForm; print('OK')"` + `python manage.py check` 통과.

---

### T3a.3 — `urls.py` 라우트 추가 (기존 보존)
**파일**: `projects/urls.py`
**작업**:
- **기존 라우트를 모두 유지** (JD, Submission, Interview, Offer, Posting, Approval, Context, Resume)
- 새 라우트를 기존 라우트 사이에 삽입
- **기존 URL name 유지** (`project_update` 그대로 — `project_edit`으로 변경하지 않음)

**추가 대상** (기존 `urlpatterns`에 삽입):

```python
# Phase 3a: 신규 라우트
path("<uuid:pk>/close/", views.project_close, name="project_close"),
path("<uuid:pk>/reopen/", views.project_reopen, name="project_reopen"),
path("<uuid:pk>/applications/", views.project_applications_partial, name="project_applications"),
path("<uuid:pk>/timeline/", views.project_timeline_partial, name="project_timeline"),

# Phase 3b: Application CRUD (stub view 연결)
path("<uuid:pk>/add_candidate/", views.project_add_candidate, name="project_add_candidate"),
path("applications/<uuid:pk>/drop/", views.application_drop, name="application_drop"),
path("applications/<uuid:pk>/restore/", views.application_restore, name="application_restore"),
path("applications/<uuid:pk>/hire/", views.application_hire, name="application_hire"),

# Phase 3b: ActionItem CRUD (stub view 연결)
path("applications/<uuid:pk>/actions/", views.application_actions_partial, name="application_actions"),
path("applications/<uuid:pk>/actions/new/", views.action_create, name="action_create"),
path("actions/<uuid:pk>/complete/", views.action_complete, name="action_complete"),
path("actions/<uuid:pk>/skip/", views.action_skip, name="action_skip"),
path("actions/<uuid:pk>/reschedule/", views.action_reschedule, name="action_reschedule"),
path("actions/<uuid:pk>/propose_next/", views.action_propose_next, name="action_propose_next"),
```

**삭제 대상**: Phase 3a에서는 삭제하지 않음. Phase 3b에서 레거시 라우트 제거.

**대시보드**: `projects/urls.py`에 추가하지 않음 → T3a.3b에서 `main/urls.py` 수정.

---

### T3a.3b — `main/urls.py` 대시보드 라우트 교체
**파일**: `main/urls.py`
**작업**: 기존 대시보드 뷰를 새 구현으로 교체.

```python
# 기존 (제거 대상)
from projects.views import dashboard as old_dashboard
path("dashboard/", old_dashboard, name="dashboard"),

# 교체
from projects.views import dashboard, dashboard_todo_partial
path("dashboard/", dashboard, name="dashboard"),
path("dashboard/todo/", dashboard_todo_partial, name="dashboard_todo"),
```

기존 `/dashboard/actions/`, `/dashboard/team/` 등은 유지하되, Phase 4a 이후 정리 대상으로 표시.

**검증**: `http://localhost:8000/dashboard/` → 200.

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


def project_add_candidate(request, pk):
    return HttpResponseNotAllowed(["POST"])


def application_drop(request, pk):
    return HttpResponseNotAllowed(["POST"])


def application_restore(request, pk):
    return HttpResponseNotAllowed(["POST"])


def application_hire(request, pk):
    return HttpResponseNotAllowed(["POST"])


def application_actions_partial(request, pk):
    return HttpResponseNotAllowed(["GET"])


def action_create(request, pk):
    return HttpResponseNotAllowed(["POST"])


def action_complete(request, pk):
    return HttpResponseNotAllowed(["POST"])


def action_skip(request, pk):
    return HttpResponseNotAllowed(["POST"])


def action_reschedule(request, pk):
    return HttpResponseNotAllowed(["POST"])


def action_propose_next(request, pk):
    return HttpResponseNotAllowed(["POST"])
```

---

### T3a.5 — `dashboard` 뷰 구현
**파일**: `projects/views.py`
**작업**:
```python
from accounts.decorators import membership_required
from accounts.helpers import _get_org

from projects.services.dashboard import (
    get_today_actions,
    get_overdue_actions,
    get_upcoming_actions,
)


@login_required
@membership_required
def dashboard(request):
    org = _get_org(request)
    user = request.user
    context = {
        "today_actions": get_today_actions(user, org),
        "overdue_actions": get_overdue_actions(user, org),
        "upcoming_actions": get_upcoming_actions(user, org, days=3),
    }
    return render(request, "projects/dashboard/index.html", context)


@login_required
@membership_required
def dashboard_todo_partial(request):
    """HTMX partial, 할 일 리스트만 반환."""
    org = _get_org(request)
    user = request.user
    scope = request.GET.get("scope", "today")
    if scope == "overdue":
        actions = get_overdue_actions(user, org)
    elif scope == "upcoming":
        actions = get_upcoming_actions(user, org)
    else:
        actions = get_today_actions(user, org)
    return render(
        request,
        "projects/partials/dashboard_todo_list.html",
        {"actions": actions, "scope": scope},
    )
```

**템플릿 placeholder**: Phase 4a에서 구현될 `dashboard/index.html`과 `partials/dashboard_todo_list.html`이 아직 없으므로, 최소 placeholder만 생성:

```bash
mkdir -p projects/templates/projects/dashboard
mkdir -p projects/templates/projects/partials
```

`projects/templates/projects/dashboard/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Dashboard (Phase 4a에서 구현)</h1>
<p>Today: {{ today_actions|length }}</p>
<p>Overdue: {{ overdue_actions|length }}</p>
<p>Upcoming: {{ upcoming_actions|length }}</p>
{% endblock %}
```

---

### T3a.6 — `project_list` 칸반 뷰 재작성
**파일**: `projects/views.py`
**작업**: 기존 `project_list` 함수를 재작성.

```python
from projects.services.dashboard import get_project_kanban_cards


@login_required
@membership_required
def project_list(request):
    org = _get_org(request)

    # 역할 기반 필터링 (기존 패턴 유지)
    membership = request.user.membership
    is_owner = membership.role == "owner"

    cards = get_project_kanban_cards(org)

    # consultant는 배정된 프로젝트만 표시
    if not is_owner:
        for phase_key in cards:
            cards[phase_key] = [
                card for card in cards[phase_key]
                if request.user in card["project"].assigned_consultants.all()
            ]

    # 필터 쿼리 파라미터 적용
    phase_filter = request.GET.get("phase")
    consultant_filter = request.GET.get("consultant") if is_owner else ""
    client_filter = request.GET.get("client")

    context = {
        "kanban": cards,
        "phase_filter": phase_filter,
        "consultant_filter": consultant_filter,
        "client_filter": client_filter,
        "is_owner": is_owner,
    }
    return render(request, "projects/project_list.html", context)
```

**기존 `project_list` 구현체를 덮어쓰기**. 기존 코드는 `ProjectStatus` 기반 필터링이므로 전체 교체. 역할 기반 필터링 패턴은 보존.

---

### T3a.7 — `project_detail` 뷰 재작성
**파일**: `projects/views.py`
**작업**:
```python
from projects.models import Application, ActionItem, ActionItemStatus, Project


@login_required
@membership_required
def project_detail(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    applications = (
        Application.objects.filter(project=project)
        .select_related("candidate")
        .prefetch_related("action_items__action_type")
        .order_by(
            models.Case(
                models.When(dropped_at__isnull=True, hired_at__isnull=True, then=0),
                models.When(hired_at__isnull=False, then=1),
                default=2,
            ),
            "-created_at",
        )  # 활성 → hired → dropped 순
    )
    context = {
        "project": project,
        "applications": applications,
    }
    return render(request, "projects/project_detail.html", context)


@login_required
@membership_required
def project_applications_partial(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    applications = Application.objects.filter(project=project).select_related("candidate")
    return render(
        request,
        "projects/partials/project_applications_list.html",
        {"project": project, "applications": applications},
    )


@login_required
@membership_required
def project_timeline_partial(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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

### T3a.8 — `project_create` / `project_update` 재작성
**파일**: `projects/views.py`
**작업**: **기존 충돌 감지 + 승인 워크플로 유지**. 새 모델 필드만 반영.

```python
from projects.forms import ProjectForm


@login_required
@membership_required
def project_create(request):
    org = _get_org(request)
    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, organization=org)
        if form.is_valid():
            # 기존 충돌 감지 로직 유지
            from projects.services.collision import detect_collisions
            collisions = detect_collisions(form.cleaned_data, org)
            if collisions and not request.POST.get("force_create"):
                return render(request, "projects/project_form.html", {
                    "form": form,
                    "mode": "create",
                    "collisions": collisions,
                })

            project = form.save(commit=False)
            project.organization = org
            project.created_by = request.user
            project.save()
            form.save_m2m()

            # 기존 승인 워크플로 유지 (해당하는 경우)
            # ... (기존 project_create의 approval 로직 보존)

            return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm(organization=org)
    return render(request, "projects/project_form.html", {"form": form, "mode": "create"})


@login_required
@membership_required
def project_update(request, pk):
    """기존 URL name `project_update` 유지."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, instance=project, organization=org)
        if form.is_valid():
            form.save()
            return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm(instance=project, organization=org)
    return render(request, "projects/project_form.html", {"form": form, "mode": "edit", "project": project})
```

**주의**: 기존 `project_create`/`project_update`를 덮어쓰되, 충돌 감지와 승인 로직은 기존 코드에서 복사하여 보존.

---

### T3a.9 — `project_close` / `project_reopen` 구현
**파일**: `projects/views.py`
**작업**:

**권한 규칙**: create/edit/close/reopen은 owner + assigned consultant 가능. delete는 owner only (기존 유지).

```python
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from projects.forms import ProjectCloseForm
from projects.models import ProjectStatus, ProjectResult
from projects.services.phase import compute_project_phase


@login_required
@membership_required
@require_http_methods(["POST"])
def project_close(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 권한 체크: owner 또는 assigned consultant
    membership = request.user.membership
    is_owner = membership.role == "owner"
    is_assigned = project.assigned_consultants.filter(pk=request.user.pk).exists()
    if not (is_owner or is_assigned):
        return HttpResponseForbidden("권한이 없습니다.")

    form = ProjectCloseForm(request.POST)
    if not form.is_valid():
        return render(request, "projects/partials/project_close_modal.html", {
            "form": form, "project": project,
        })

    # status와 closed_at을 함께 저장 (CHECK constraint 준수)
    project.closed_at = timezone.now()
    project.status = ProjectStatus.CLOSED
    project.result = form.cleaned_data["result"]
    project.note = form.cleaned_data["note"]
    project.save(update_fields=["closed_at", "status", "result", "note", "updated_at"])

    # pending ActionItem을 일괄 CANCELLED (dashboard 잔류 방지)
    from projects.models import ActionItem, ActionItemStatus
    ActionItem.objects.filter(
        application__project=project,
        status=ActionItemStatus.PENDING,
    ).update(status=ActionItemStatus.CANCELLED)

    return redirect("projects:project_detail", pk=project.pk)


@login_required
@membership_required
@require_http_methods(["POST"])
def project_reopen(request, pk):
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 권한 체크
    membership = request.user.membership
    is_owner = membership.role == "owner"
    is_assigned = project.assigned_consultants.filter(pk=request.user.pk).exists()
    if not (is_owner or is_assigned):
        return HttpResponseForbidden("권한이 없습니다.")

    project.closed_at = None
    project.status = ProjectStatus.OPEN
    project.result = ""
    project.save(update_fields=["closed_at", "status", "result", "updated_at"])

    # phase 재계산 (signal이 ActionItem/Application 변경 시에만 작동하므로 명시적 호출)
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])

    return redirect("projects:project_detail", pk=project.pk)
```

---

### T3a.10 — `views.py`의 레거시 참조 확인
**작업**:
```bash
grep -n "ProjectStatus\|lifecycle\|Contact\|Offer" projects/views.py
```

Phase 3a 대상 메인 뷰에서는 레거시 import 제거. Phase 3b 대상 코드(offer_*, status_update 등)는 그대로 남아있어도 무방 (Phase 3b에서 삭제).

`views.py` import 섹션에서 `from projects.services.lifecycle import ...` 같은 import가 있으면 **이 Phase에서 반드시 제거**. 남아있으면 ImportError.

---

### T3a.11 — `manage.py check` + `runserver` 스모크 확인
**작업**:
```bash
uv run python manage.py check
```

**예상**:
- 에러 0건 (views 레이어까지)
- `forms.py` 기존 폼이 정상 import됨

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

**수동 확인**:
- `http://localhost:8000/dashboard/` → 200, placeholder 렌더
- `http://localhost:8000/projects/` → 200, 칸반
- `http://localhost:8000/projects/new/` → 200, 생성 폼 (충돌 감지 동작)
- 관리자 페이지 접근 가능

---

## 5. 검증 체크리스트

- [ ] `forms.py`에 새 폼 존재, **기존 폼 보존** (OfferForm, SubmissionForm 등)
- [ ] `urls.py`에 새 라우트 등록, **기존 라우트 보존**
- [ ] `main/urls.py`에서 대시보드 뷰 교체 완료
- [ ] `views.py`의 dashboard, project_list, project_detail, project_create, project_update, project_close, project_reopen 재작성 완료
- [ ] **모든 신규 뷰에 `@membership_required` + `_get_org(request)` 적용**
- [ ] **대시보드 서비스 호출에 `org` 인자 전달**
- [ ] **project_list에 역할 기반 필터링 적용** (owner: 전체, consultant: assigned only)
- [ ] **project_close에서 `status=CLOSED` 명시적 설정** (CHECK constraint 준수)
- [ ] **project_close에서 pending ActionItem 일괄 CANCELLED**
- [ ] **project_reopen에서 `compute_project_phase()` 호출**
- [ ] **project_create에서 충돌 감지 + 승인 워크플로 보존**
- [ ] **ProjectForm에 `organization=org` 인자 전달**
- [ ] **close/reopen 권한 체크** (owner + assigned consultant)
- [ ] Phase 3b 대상 뷰가 stub으로 존재 (urls.py import 성공)
- [ ] `views.py`에서 `from projects.services.lifecycle import` 제거
- [ ] `python manage.py check` 통과
- [ ] `runserver` 기동 성공
- [ ] `/dashboard/`, `/projects/`, `/projects/new/` URL 200 응답

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `views.py`가 3,030줄이라 단일 세션에서 전체 파악 어려움 | T3a.1 인벤토리로 분할 지도 확보. 섹션별 순차 편집 |
| 기존 `project_list` 등 뷰의 context가 템플릿과 shape 달라서 깨짐 | Phase 4a 이전에는 placeholder 템플릿만 쓰므로 context만 맞으면 OK |
| stub 함수 signature 불일치로 urls.py 로딩 실패 | 모든 stub에 `(request, pk)` signature 통일 + `HttpResponseNotAllowed` 반환 |
| 기존 충돌 감지/승인 로직 복잡도 | 기존 `project_create` 코드에서 직접 복사하여 보존 |
| 기존 `urls.py`의 유지 대상 라우트 누락 | 기존 라우트를 절대 삭제하지 않음. 추가만. |
| `views.py`의 기존 JD/Approval/Search 뷰에도 간접적으로 lifecycle 호출이 있을 수 있음 | grep으로 발견 시 해당 호출 제거, 로직이 필요하면 새 서비스로 치환 |
| `project_close` CHECK constraint | `status=CLOSED` 명시 설정으로 해결 |
| consultant가 전체 프로젝트 열람 | 뷰 레벨에서 역할 기반 필터링 적용 |

## 7. 커밋 포인트

```
feat(projects): add new forms + rewrite main views (dashboard/kanban/detail)

- Add new forms: ApplicationCreateForm, ApplicationDropForm,
  ProjectCloseForm, ActionItem*Form (preserve existing forms)
- Add new routes to urls.py (preserve existing routes)
- Replace dashboard views in main/urls.py
- Rewrite views.py main section: dashboard, dashboard_todo_partial,
  project_list (2-phase kanban with role-based scoping),
  project_detail, project_applications_partial,
  project_timeline_partial, project_create (preserve collision/approval),
  project_update, project_close (with CHECK constraint fix
  + ActionItem cancellation), project_reopen (with phase recalculation)
- Add stubs for Phase 3b views (application_*, action_*)
- Apply @membership_required + _get_org() to all new views

Refs: FINAL-SPEC.md §5
```

## 8. Phase 3b로 넘기는 인터페이스

- 메인 뷰가 동작
- Application·ActionItem 라우트는 URL에 등록됨, stub이 존재
- Phase 3b는 각 stub을 실제 구현으로 교체 + `project_add_candidate` 구현 + 레거시 제거
- 기존 폼 정리 (OfferForm, ProjectStatusForm 등 삭제)는 Phase 3b

---

**이전 Phase**: [phase-2b-services-cleanup.md](phase-2b-services-cleanup.md)
**다음 Phase**: [phase-3b-views-crud.md](phase-3b-views-crud.md)

<!-- forge:phase-3a-views-base:impl-plan:complete:2026-04-14T18:40:00Z -->
