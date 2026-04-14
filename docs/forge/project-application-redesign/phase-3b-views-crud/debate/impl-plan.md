# Phase 3b — Application/ActionItem CRUD 뷰 + 레거시 제거

**전제**: [Phase 3a](phase-3a-views-base.md) 완료. 메인 뷰와 stub이 동작.
**목표**: Phase 3a에서 stub으로 둔 Application·ActionItem CRUD 뷰를 모두 실제 구현으로 교체. `views_voice.py` 수정. 기존 offer·status_update·contact 뷰 완전 제거.
**예상 시간**: 0.5-1일
**리스크**: 중

---

## 1. 목표 상태

- `views.py`의 stub 함수 10개가 모두 실제 구현으로 교체
- `views_voice.py`가 ActionItem 기반 플로우와 연동
- `views.py`에서 `offer_*`, `status_update`, `contact_*` 함수 완전 제거
- `urls.py`에서 위 라우트 제거
- `views.py`에서 `ProjectStatus`, `Contact`, `Offer` grep 결과 0건
- `python manage.py check` 통과
- `runserver` 기동 후 Application 추가 → ActionItem 생성·완료 → 드롭 플로우가 placeholder 응답으로 동작 (실제 UI는 Phase 4)

## 2. 사전 조건

- Phase 3a 커밋 완료
- `services/application_lifecycle.py`, `services/action_lifecycle.py` 함수 사용 가능
- `forms.py`의 `ApplicationCreateForm`, `ApplicationDropForm`, `ActionItemCreateForm`, `ActionItemCompleteForm`, `ActionItemSkipForm`, `ActionItemRescheduleForm` 정의됨

## 3. 영향 범위

### 3.1 수정 파일
- `projects/views.py` (Phase 3b 섹션 본체 작성 + 레거시 함수 삭제)
- `projects/views_voice.py` (수정)
- `projects/urls.py` (offer/status_update/contact 라우트 제거)

### 3.2 영향 받는 템플릿
- 기존 offer/status_update/contact 템플릿은 Phase 4b에서 삭제 (여기서는 view·url 레벨만 정리)

## 4. 태스크 분할

### T3b.1 — `project_add_candidate` 구현
**파일**: `projects/views.py`
**작업**:
```python
from projects.forms import ApplicationCreateForm
from projects.models import Application, Project
from projects.services.auto_actions import suggest_initial_action  # optional


@login_required
def project_add_candidate(request, pk):
    project = get_object_or_404(Project, pk=pk, organization=request.user.organization)
    if request.method == "GET":
        form = ApplicationCreateForm()
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
        )
    # POST
    form = ApplicationCreateForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
            status=400,
        )
    candidate = form.cleaned_data["candidate"]
    if Application.objects.filter(project=project, candidate=candidate).exists():
        form.add_error("candidate", "이미 매칭된 후보자입니다.")
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
            status=400,
        )
    application = Application.objects.create(
        project=project,
        candidate=candidate,
        notes=form.cleaned_data.get("notes", ""),
        created_by=request.user,
    )
    # 후속 제안: signal이 phase 재계산. Initial action은 UI에서 별도 생성
    return redirect("projects:project_detail", pk=project.pk)
```

**검증**: POST 시 Application 생성, 중복 시 에러, GET 시 모달 partial 반환.

---

### T3b.2 — `application_drop` / `restore` / `hire` 구현
**파일**: `projects/views.py`
**작업**:
```python
from projects.forms import ApplicationDropForm
from projects.services.application_lifecycle import drop, restore, hire


@login_required
@require_POST
def application_drop(request, pk):
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=request.user.organization,
    )
    form = ApplicationDropForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
            status=400,
        )
    drop(
        application,
        reason=form.cleaned_data["drop_reason"],
        actor=request.user,
        note=form.cleaned_data.get("drop_note", ""),
    )
    return render(
        request,
        "projects/partials/application_card.html",
        {"application": application, "swap_target": "outerHTML"},
    )


@login_required
@require_POST
def application_restore(request, pk):
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=request.user.organization,
    )
    restore(application, actor=request.user)
    return render(
        request,
        "projects/partials/application_card.html",
        {"application": application},
    )


@login_required
@require_POST
def application_hire(request, pk):
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=request.user.organization,
    )
    hire(application, actor=request.user)
    # signal이 프로젝트 자동 종료 + 나머지 드롭
    return redirect("projects:project_detail", pk=application.project.pk)
```

**`require_POST` import**:
```python
from django.views.decorators.http import require_POST
```

---

### T3b.3 — `application_actions_partial` 구현
**파일**: `projects/views.py`
**작업**:
```python
@login_required
def application_actions_partial(request, pk):
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=request.user.organization,
    )
    return render(
        request,
        "projects/partials/application_actions_list.html",
        {"application": application, "actions": application.action_items.all()},
    )
```

---

### T3b.4 — `action_create` 구현
**파일**: `projects/views.py`
**작업**:
```python
from projects.forms import ActionItemCreateForm
from projects.models import ActionType
from projects.services.action_lifecycle import create_action


@login_required
def action_create(request, pk):
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=request.user.organization,
    )
    if request.method == "GET":
        active_types = ActionType.objects.filter(is_active=True).order_by("sort_order")
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"application": application, "action_types": active_types},
        )
    # POST
    form = ActionItemCreateForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"form": form, "application": application},
            status=400,
        )
    action_type = get_object_or_404(ActionType, pk=form.cleaned_data["action_type_id"], is_active=True)
    create_action(
        application,
        action_type,
        actor=request.user,
        title=form.cleaned_data.get("title", ""),
        channel=form.cleaned_data.get("channel", ""),
        scheduled_at=form.cleaned_data.get("scheduled_at"),
        due_at=form.cleaned_data.get("due_at"),
        note=form.cleaned_data.get("note", ""),
    )
    return render(
        request,
        "projects/partials/application_card.html",
        {"application": application},
    )
```

---

### T3b.5 — `action_complete` 구현
**파일**: `projects/views.py`
**작업**:
```python
from projects.forms import ActionItemCompleteForm
from projects.models import ActionItem
from projects.services.action_lifecycle import complete_action, propose_next


@login_required
@require_POST
def action_complete(request, pk):
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=request.user.organization,
    )
    form = ActionItemCompleteForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action},
            status=400,
        )
    complete_action(
        action,
        actor=request.user,
        result=form.cleaned_data.get("result", ""),
        note=form.cleaned_data.get("note", ""),
    )
    suggestions = propose_next(action)
    return render(
        request,
        "projects/partials/action_propose_next_modal.html",
        {
            "completed_action": action,
            "suggestions": suggestions,
        },
    )
```

---

### T3b.6 — `action_skip` / `reschedule` / `propose_next` 구현
**파일**: `projects/views.py`
**작업**:
```python
from projects.forms import ActionItemSkipForm, ActionItemRescheduleForm
from projects.services.action_lifecycle import skip_action, reschedule_action


@login_required
@require_POST
def action_skip(request, pk):
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=request.user.organization,
    )
    form = ActionItemSkipForm(request.POST)
    if form.is_valid():
        skip_action(action, actor=request.user, note=form.cleaned_data.get("note", ""))
    return render(
        request,
        "projects/partials/action_item_card.html",
        {"action": action},
    )


@login_required
@require_POST
def action_reschedule(request, pk):
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=request.user.organization,
    )
    form = ActionItemRescheduleForm(request.POST)
    if form.is_valid():
        reschedule_action(
            action,
            actor=request.user,
            new_due_at=form.cleaned_data.get("new_due_at"),
            new_scheduled_at=form.cleaned_data.get("new_scheduled_at"),
        )
    return render(
        request,
        "projects/partials/action_item_card.html",
        {"action": action},
    )


@login_required
@require_POST
def action_propose_next(request, pk):
    """완료된 액션 다음에 컨설턴트가 선택한 후속 액션들을 생성."""
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=request.user.organization,
    )
    selected_ids = request.POST.getlist("next_action_type_ids")
    new_actions = []
    for type_id in selected_ids:
        try:
            action_type = ActionType.objects.get(pk=type_id, is_active=True)
        except ActionType.DoesNotExist:
            continue
        new_action = create_action(
            action.application,
            action_type,
            actor=request.user,
            parent_action=action,
        )
        new_actions.append(new_action)
    return render(
        request,
        "projects/partials/application_actions_list.html",
        {"application": action.application, "actions": action.application.action_items.all()},
    )
```

---

### T3b.7 — `views_voice.py` 수정
**파일**: `projects/views_voice.py`
**작업**:
- `ProjectStatus` import 제거
- "홍길동을 삼성전자 프로젝트에 추가해줘" 같은 명령을 Application 생성으로 연결:
  - 후보자 검색 → 없으면 새 Candidate 생성 (대화형)
  - 프로젝트 검색
  - `Application.objects.create(project=, candidate=, created_by=)`
- 기존 voice intent handler 중 status 변경 명령은 제거 (phase 자동 파생)
- 기존 voice intent handler 중 Application/ActionItem 생성 의도는 새 함수 사용

**검증**: voice 관련 테스트 또는 수동 호출로 Application 생성 확인.

---

### T3b.8 — 레거시 함수 제거
**파일**: `projects/views.py`
**작업**:
1. `offer_*` 함수 전체 제거 (`offer_create`, `offer_update`, `offer_list`, `offer_detail`, `offer_status_update` 등)
2. `status_update` 함수 제거
3. `contact_*` 직접 CRUD 함수 제거 (있다면; reach_out ActionItem으로 대체)
4. 미사용 import 정리

**확인**:
```bash
grep -n "def offer_\|def status_update\|def contact_" projects/views.py
```
→ 결과 0건.

---

### T3b.9 — `urls.py` 레거시 라우트 제거
**파일**: `projects/urls.py`
**작업**:
- `path("<uuid:pk>/status/", ...)` 제거
- `path("<uuid:pk>/offer/", ...)` 계열 전체 제거
- `path("contacts/...)` 직접 CRUD 제거

**검증**:
```bash
uv run python manage.py show_urls | grep -E "offer|status_update|contact"
```
→ 결과 0건.

---

### T3b.10 — `views.py` 잔여 ProjectStatus·Contact·Offer grep
**작업**:
```bash
grep -n "ProjectStatus\|class Contact\b\|class Offer\b\|models\.Offer\b\|from .*import.*Offer\b" projects/views.py
```
→ 결과 0건.

남아있으면 즉시 정리.

---

### T3b.11 — `python manage.py check` + 스모크
**작업**:
```bash
uv run python manage.py check
uv run python manage.py runserver 0.0.0.0:8000
```

**수동 확인**:
- `/projects/<id>/add_candidate/` POST → Application 생성 (curl 또는 admin 통해)
- `/applications/<id>/drop/` POST → 드롭
- `/applications/<id>/hire/` POST → 입사 + 자동 종료 확인
- `/applications/<id>/actions/new/` POST → ActionItem 생성

(템플릿은 placeholder이므로 200 응답만 확인. 실제 UI는 Phase 4b)

---

## 5. 검증 체크리스트

- [ ] `project_add_candidate` 구현
- [ ] `application_drop`, `application_restore`, `application_hire` 구현
- [ ] `application_actions_partial` 구현
- [ ] `action_create`, `action_complete`, `action_skip`, `action_reschedule`, `action_propose_next` 구현
- [ ] `views_voice.py` 수정 완료
- [ ] `offer_*`, `status_update`, `contact_*` 함수 전부 제거
- [ ] `urls.py`에서 위 라우트 제거
- [ ] `grep ProjectStatus projects/views.py` → 0건
- [ ] `grep "models\.Offer\|class Offer" projects/views.py` → 0건
- [ ] `python manage.py check` 통과
- [ ] `runserver` 기동 + 주요 엔드포인트 200 응답 (또는 405 POST-only)

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `views_voice.py`에 의도된 동작이 모호 | 기존 voice 라우팅 코드 분석 후 ProjectStatus 기반 명령은 모두 무력화. 새 명령 추가는 Phase 4 이후로 미룸 |
| `action_complete` 응답이 후속 제안 모달인데 Phase 4b 모달이 아직 없음 | placeholder 모달로 200 응답만 보장. 실제 UI는 Phase 4b |
| Permission 검사 중복 | `request.user.organization` 일관 사용. 필요 시 helper로 추출 |
| `require_POST` 데코레이터로 GET 요청 405 | 정상 동작. 모달 GET이 필요한 view는 별도 분기 |
| 후보자 검색 모달 API 없음 (`add_candidate_modal`) | Phase 4b에서 검색 결과 partial 추가. Phase 3b는 form select 기본 위젯으로 충분 |

## 7. 커밋 포인트

```
feat(projects): implement Application/ActionItem CRUD views + remove legacy

- Implement project_add_candidate (Application creation)
- Implement application_drop/restore/hire endpoints
- Implement action_create/complete/skip/reschedule/propose_next endpoints
- Update views_voice.py to use Application/ActionItem flow
- Remove offer_*, status_update, contact_* views entirely
- Remove corresponding URL routes
- views.py free of ProjectStatus/Contact/Offer references

Refs: FINAL-SPEC.md §5
```

## 8. Phase 4a로 넘기는 인터페이스

- 모든 뷰가 동작 (placeholder 템플릿이지만 200/405 응답 일관)
- 템플릿 경로가 모두 확정됨 (`projects/dashboard/index.html`, `projects/project_list.html`, `projects/project_detail.html`, 다수 partial)
- Phase 4a는 이 템플릿 파일들을 실제 UI로 채우는 작업

---

**이전 Phase**: [phase-3a-views-base.md](phase-3a-views-base.md)
**다음 Phase**: [phase-4a-templates-core.md](phase-4a-templates-core.md)
