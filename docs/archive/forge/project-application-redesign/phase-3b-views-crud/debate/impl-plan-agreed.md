# Phase 3b — Application/ActionItem CRUD 뷰 + 레거시 제거

**전제**: [Phase 3a](phase-3a-views-base.md) 완료. 메인 뷰와 stub이 동작.
**목표**: Phase 3a에서 stub으로 둔 Application·ActionItem CRUD 뷰를 모두 실제 구현으로 교체. `views_voice.py` + voice 서비스 수정. 기존 offer·status_update·contact 뷰/라우트 완전 제거. legacy tab 뷰 정리.
**예상 시간**: 0.5-1일
**리스크**: 중

---

## 1. 목표 상태

- `views.py`의 stub 함수 10개가 모두 실제 구현으로 교체
- 모든 CRUD 뷰가 `@membership_required` + `_get_org()` 패턴 사용 (기존 코드베이스 일관성)
- 모든 lifecycle 서비스 호출에 `try/except ValueError` 에러 핸들링
- HTMX 요청 시 `HX-Redirect` / `HX-Trigger` 헤더 사용 (Django redirect 대신)
- `views_voice.py` + `services/voice/action_executor.py` + `intent_parser.py`에서 legacy intent 제거/비활성화
- `views.py`에서 `offer_*`, `status_update`, `contact_*` 함수 완전 제거
- `project_tab_contacts`, `project_tab_offers` 뷰를 제거/스텁 교체
- `urls.py`에서 위 라우트 제거 + 관련 tab URL도 정리
- `detail_tab_bar.html`에서 contacts/offers 탭 숨김/제거
- `tab_overview.html`에서 contacts/offers 링크 제거
- `views.py`에서 `Contact`, `Offer` grep 결과 0건 (ProjectStatus는 유효한 라이브 enum이므로 유지)
- `python manage.py check` 통과
- 모든 새 partial 템플릿에 placeholder 파일 존재
- 기본 smoke test + 에러 경로 테스트 통과

## 2. 사전 조건

- Phase 3a 커밋 완료
- `services/application_lifecycle.py`, `services/action_lifecycle.py` 함수 사용 가능
- `forms.py`의 `ApplicationCreateForm`, `ApplicationDropForm`, `ActionItemCreateForm`, `ActionItemCompleteForm`, `ActionItemSkipForm`, `ActionItemRescheduleForm` 정의됨

## 3. 영향 범위

### 3.1 수정 파일
- `projects/views.py` (Phase 3b 섹션 본체 작성 + 레거시 함수 삭제 + tab 뷰 스텁)
- `projects/views_voice.py` (수정)
- `projects/services/voice/action_executor.py` (legacy intent 비활성화)
- `projects/services/voice/intent_parser.py` (legacy intent 제거)
- `projects/services/application_lifecycle.py` (create_application 추가)
- `projects/urls.py` (offer/status_update/contact 라우트 제거 + tab_contacts/tab_offers 라우트 정리)
- `projects/templates/projects/partials/detail_tab_bar.html` (contacts/offers 탭 숨김)
- `projects/templates/projects/partials/tab_overview.html` (contacts/offers 링크 제거)

### 3.2 신규 placeholder 템플릿 (Phase 4에서 실제 UI 구현)
- `projects/templates/projects/partials/add_candidate_modal.html`
- `projects/templates/projects/partials/drop_application_modal.html`
- `projects/templates/projects/partials/application_card.html`
- `projects/templates/projects/partials/application_actions_list.html`
- `projects/templates/projects/partials/action_create_modal.html`
- `projects/templates/projects/partials/action_complete_modal.html`
- `projects/templates/projects/partials/action_propose_next_modal.html`
- `projects/templates/projects/partials/action_item_card.html`

### 3.3 영향 받는 템플릿
- 기존 offer/contact 전용 템플릿은 Phase 4b에서 삭제 (여기서는 view·url·tab 참조만 정리)

## 4. 태스크 분할

### T3b.0 — `create_application` 서비스 함수 추가
**파일**: `projects/services/application_lifecycle.py`
**작업**: Application 생성을 서비스 레이어로 이동. web view와 voice view 모두 이 함수를 호출.
```python
from django.db import IntegrityError, transaction


def create_application(
    project: Project,
    candidate,
    actor,
    *,
    notes: str = "",
) -> Application:
    """Create Application with guards. Single entry point for web + voice."""
    # guard: closed project
    if project.closed_at is not None:
        raise ValueError("cannot add candidate to a closed project")
    # guard: inactive application (already exists, dropped or hired)
    # DB UniqueConstraint handles true duplicates

    try:
        with transaction.atomic():
            application = Application.objects.create(
                project=project,
                candidate=candidate,
                notes=notes,
                created_by=actor,
            )
    except IntegrityError:
        raise ValueError("이미 매칭된 후보자입니다.")
    return application
```

**검증**: 중복 candidate → ValueError, 종료된 project → ValueError.

---

### T3b.1 — `project_add_candidate` 구현
**파일**: `projects/views.py`
**HTMX 계약**: GET → 모달 partial 반환, POST 성공 → HX-Trigger: applicationChanged, POST 실패 → 400 + 모달 partial with errors

**작업**:
```python
from django.views.decorators.http import require_POST

from accounts.decorators import membership_required
from accounts.helpers import _get_org
from projects.forms import ApplicationCreateForm
from projects.models import Application, Project
from projects.services.application_lifecycle import create_application


@membership_required
def project_add_candidate(request, pk):
    """POST /projects/<pk>/add_candidate/ — Application 생성.
    GET: 후보자 추가 모달 폼 렌더링.
    POST: Application 생성 → HX-Trigger: applicationChanged.
    """
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "GET":
        form = ApplicationCreateForm(organization=org)
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
        )

    # POST
    form = ApplicationCreateForm(request.POST, organization=org)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
            status=400,
        )

    try:
        application = create_application(
            project=project,
            candidate=form.cleaned_data["candidate"],
            actor=request.user,
            notes=form.cleaned_data.get("notes", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
            status=400,
        )

    # HTMX: trigger refresh, non-HTMX: redirect
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "applicationChanged"
        return response
    return redirect("projects:project_detail", pk=project.pk)
```

**검증**: POST 시 Application 생성, 중복 시 400 에러, GET 시 모달 partial 반환, org 스코핑 확인.

---

### T3b.2 — `application_drop` / `restore` / `hire` 구현
**파일**: `projects/views.py`
**HTMX 계약**:
- `drop`: GET → 드롭 사유 모달, POST → application_card 갱신 + HX-Trigger
- `restore`: POST only → application_card 갱신 + HX-Trigger
- `hire`: POST only → HX-Redirect to project detail (전체 상태 변경)

**작업**:
```python
from projects.forms import ApplicationDropForm
from projects.services.application_lifecycle import drop, restore, hire


@membership_required
def application_drop(request, pk):
    """GET: 드롭 사유 모달 렌더링. POST: Application 드롭."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
    )

    if request.method == "GET":
        form = ApplicationDropForm()
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
        )

    # POST
    form = ApplicationDropForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
            status=400,
        )
    try:
        drop(
            application,
            reason=form.cleaned_data["drop_reason"],
            actor=request.user,
            note=form.cleaned_data.get("drop_note", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "projects/partials/application_card.html",
            {"application": application},
        )
        response["HX-Trigger"] = "applicationChanged"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)


@membership_required
@require_POST
def application_restore(request, pk):
    """POST: Application 드롭 복구."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
    )
    try:
        restore(application, actor=request.user)
    except ValueError as e:
        if request.headers.get("HX-Request"):
            return HttpResponse(str(e), status=400)
        return HttpResponseBadRequest(str(e))

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "projects/partials/application_card.html",
            {"application": application},
        )
        response["HX-Trigger"] = "applicationChanged"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)


@membership_required
@require_POST
def application_hire(request, pk):
    """POST: 입사 확정. Signal이 프로젝트 자동 종료 + 나머지 드롭."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
    )
    try:
        hire(application, actor=request.user)
    except ValueError as e:
        if request.headers.get("HX-Request"):
            return HttpResponse(str(e), status=409)
        return HttpResponseBadRequest(str(e))

    # Hire changes entire project state → full page redirect
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = f"/projects/{application.project.pk}/"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)
```

**`require_POST` / `require_http_methods` import**:
```python
from django.views.decorators.http import require_POST, require_http_methods
```

---

### T3b.3 — `application_actions_partial` 구현
**파일**: `projects/views.py`
**HTMX 계약**: GET → ActionItem 목록 partial (hx-trigger="actionChanged from:body"로 자동 갱신)

**작업**:
```python
@membership_required
def application_actions_partial(request, pk):
    """GET: Application의 ActionItem 목록."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
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
**HTMX 계약**: GET → 액션 생성 모달 (ActionType 선택), POST → HX-Trigger: actionChanged

**작업**:
```python
from projects.forms import ActionItemCreateForm
from projects.models import ActionType
from projects.services.action_lifecycle import create_action


@membership_required
def action_create(request, pk):
    """GET: 액션 생성 모달. POST: ActionItem 생성."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
    )
    active_types = ActionType.objects.filter(is_active=True).order_by("sort_order")

    if request.method == "GET":
        form = ActionItemCreateForm()
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"form": form, "application": application, "action_types": active_types},
        )

    # POST
    form = ActionItemCreateForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"form": form, "application": application, "action_types": active_types},
            status=400,
        )

    action_type = get_object_or_404(
        ActionType, pk=form.cleaned_data["action_type_id"], is_active=True
    )
    try:
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
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"form": form, "application": application, "action_types": active_types},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)
```

---

### T3b.5 — `action_complete` 구현
**파일**: `projects/views.py`
**HTMX 계약**: GET → 완료 모달 (결과 입력 + 후속 제안), POST → 후속 제안 모달 or HX-Trigger: actionChanged

**작업**:
```python
from projects.forms import ActionItemCompleteForm
from projects.models import ActionItem
from projects.services.action_lifecycle import complete_action, propose_next


@membership_required
def action_complete(request, pk):
    """GET: 완료 모달 렌더링. POST: ActionItem 완료 + 후속 제안."""
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
    )

    if request.method == "GET":
        form = ActionItemCompleteForm()
        suggestions = propose_next(action) if action.status == "pending" else []
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action, "suggestions": suggestions},
        )

    # POST
    form = ActionItemCompleteForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    try:
        complete_action(
            action,
            actor=request.user,
            result=form.cleaned_data.get("result", ""),
            note=form.cleaned_data.get("note", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    suggestions = propose_next(action)
    if suggestions:
        response = render(
            request,
            "projects/partials/action_propose_next_modal.html",
            {"completed_action": action, "suggestions": suggestions},
        )
        response["HX-Trigger"] = "actionChanged"
        return response

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)
```

---

### T3b.6 — `action_skip` / `reschedule` / `propose_next` 구현
**파일**: `projects/views.py`
**HTMX 계약**:
- `skip`: GET → 건너뛰기 사유 모달, POST → action_item_card 갱신 + HX-Trigger
- `reschedule`: GET → 일정 변경 모달, POST → action_item_card 갱신 + HX-Trigger
- `propose_next`: POST only → action_list 갱신 + HX-Trigger

**작업**:
```python
from projects.forms import ActionItemSkipForm, ActionItemRescheduleForm
from projects.services.action_lifecycle import skip_action, reschedule_action


@membership_required
def action_skip(request, pk):
    """GET: 건너뛰기 사유 모달. POST: ActionItem 건너뛰기."""
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
    )

    if request.method == "GET":
        form = ActionItemSkipForm()
        return render(
            request,
            "projects/partials/action_skip_modal.html",
            {"form": form, "action": action},
        )

    # POST
    form = ActionItemSkipForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_skip_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    try:
        skip_action(action, actor=request.user, note=form.cleaned_data.get("note", ""))
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_skip_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "projects/partials/action_item_card.html",
            {"action": action},
        )
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)


@membership_required
def action_reschedule(request, pk):
    """GET: 일정 변경 모달. POST: ActionItem 일정 변경."""
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
    )

    if request.method == "GET":
        form = ActionItemRescheduleForm()
        return render(
            request,
            "projects/partials/action_reschedule_modal.html",
            {"form": form, "action": action},
        )

    # POST
    form = ActionItemRescheduleForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_reschedule_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    try:
        reschedule_action(
            action,
            actor=request.user,
            new_due_at=form.cleaned_data.get("new_due_at"),
            new_scheduled_at=form.cleaned_data.get("new_scheduled_at"),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_reschedule_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "projects/partials/action_item_card.html",
            {"action": action},
        )
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)


@membership_required
@require_POST
def action_propose_next(request, pk):
    """POST: 완료된 액션 다음에 컨설턴트가 선택한 후속 액션들을 생성.
    선택된 type IDs를 propose_next() 결과와 교차검증.
    """
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
    )

    # Guard: parent action must be completed
    if action.status != ActionItemStatus.DONE:
        if request.headers.get("HX-Request"):
            return HttpResponse("완료된 액션에서만 후속 생성이 가능합니다.", status=400)
        return HttpResponseBadRequest("완료된 액션에서만 후속 생성이 가능합니다.")

    selected_ids = request.POST.getlist("next_action_type_ids")
    if not selected_ids:
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "actionChanged"
            return response
        return redirect("projects:project_detail", pk=action.application.project.pk)

    # Validate selected IDs against allowed suggestions
    allowed_types = propose_next(action)
    allowed_ids = {str(at.pk) for at in allowed_types}
    invalid_ids = set(selected_ids) - allowed_ids
    if invalid_ids:
        if request.headers.get("HX-Request"):
            return HttpResponse("선택한 액션 유형이 허용 목록에 없습니다.", status=400)
        return HttpResponseBadRequest("선택한 액션 유형이 허용 목록에 없습니다.")

    # Atomic batch creation
    with transaction.atomic():
        new_actions = []
        for type_id in selected_ids:
            action_type = ActionType.objects.get(pk=type_id, is_active=True)
            new_action = create_action(
                action.application,
                action_type,
                actor=request.user,
                parent_action=action,
            )
            new_actions.append(new_action)

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "projects/partials/application_actions_list.html",
            {
                "application": action.application,
                "actions": action.application.action_items.all(),
            },
        )
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)
```

---

### T3b.7 — `views_voice.py` + voice 서비스 수정
**파일**: `projects/views_voice.py`, `projects/services/voice/action_executor.py`, `projects/services/voice/intent_parser.py`

**작업**:

#### 7a. `intent_parser.py`
- `VALID_INTENTS`에서 `contact_record`, `contact_reserve`, `offer_create` 제거
- `REQUIRED_ENTITIES`에서 동일 키 제거
- LLM 프롬프트에서 해당 intent 설명 제거

#### 7b. `action_executor.py`
- `_preview_contact_record`, `_confirm_contact_record` 함수 삭제
- `_preview_contact_reserve`, `_confirm_contact_reserve` 함수 삭제
- `_preview_offer_create`, `_confirm_offer_create` 함수 삭제
- `_PREVIEW_HANDLERS`와 `_CONFIRM_HANDLERS`에서 해당 키 제거
- Contact, Offer 관련 import 제거
- `check_duplicate`, `is_submission_offer_eligible` 등 삭제된 모델 의존 import 정리

#### 7c. `views_voice.py`
- ProjectStatus import 확인 → 현재 없음 (이미 깨끗)
- 기존 voice intent handler 중 status 변경 명령 확인 → 현재 없음
- Application 생성 의도 연결: `create_application` 서비스 사용하도록 action_executor에 `application_add` intent 추가 검토 (Phase 4 이후 작업으로 TODO 주석 남김)

**검증**: `grep -r "Contact\|Offer" projects/services/voice/action_executor.py` → 0건.

---

### T3b.8 — 레거시 함수 제거
**파일**: `projects/views.py`
**작업**:
1. `offer_create`, `offer_update`, `offer_delete`, `offer_accept`, `offer_reject` 함수 전체 제거
2. `status_update` 함수 제거
3. `contact_create`, `contact_update`, `contact_delete`, `contact_reserve`, `contact_release_lock`, `contact_check_duplicate` 함수 전체 제거
4. `project_tab_contacts` 함수를 빈 placeholder로 교체:
   ```python
   @membership_required
   def project_tab_contacts(request, pk):
       """Legacy: 컨택 탭 제거됨. ActionItem으로 대체."""
       return HttpResponse('<div class="p-4 text-gray-500">이 기능은 ActionItem으로 대체되었습니다.</div>')
   ```
5. `project_tab_offers` 함수를 빈 placeholder로 교체:
   ```python
   @membership_required
   def project_tab_offers(request, pk):
       """Legacy: 오퍼 탭 제거됨. ActionItem으로 대체."""
       return HttpResponse('<div class="p-4 text-gray-500">이 기능은 ActionItem으로 대체되었습니다.</div>')
   ```
6. `_DeletedModelSentinel` 클래스와 sentinel 인스턴스 제거
7. 미사용 import 정리 (ContactForm, OfferForm, SubmissionFeedbackForm 등)

**확인**:
```bash
grep -n "def offer_\|def status_update\|def contact_create\|def contact_update\|def contact_delete\|def contact_reserve\|def contact_release_lock\|def contact_check_duplicate" projects/views.py
```
→ 결과 0건.

---

### T3b.9 — `urls.py` 레거시 라우트 제거
**파일**: `projects/urls.py`
**작업**:
- `path("<uuid:pk>/status/", ...)` 제거
- `path("<uuid:pk>/offers/...", ...)` 계열 5개 전체 제거
- `path("<uuid:pk>/contacts/...", ...)` 직접 CRUD 6개 전체 제거
- `project_tab_contacts`, `project_tab_offers` URL은 유지 (stub 함수가 응답하므로 NoReverseMatch 방지)

**검증**:
```bash
uv run python manage.py show_urls | grep -E "offer_create|offer_update|offer_delete|offer_accept|offer_reject|status_update|contact_create|contact_update|contact_delete|contact_reserve|contact_release|contact_check"
```
→ 결과 0건.

---

### T3b.10 — `detail_tab_bar.html` + `tab_overview.html` 정리
**파일**:
- `projects/templates/projects/partials/detail_tab_bar.html`
- `projects/templates/projects/partials/tab_overview.html`

**작업**:
1. `detail_tab_bar.html`에서 contacts/offers 탭 버튼을 주석 처리 또는 제거
2. `tab_overview.html`에서 contacts/offers 관련 링크 (project_tab_contacts, project_tab_offers URL 사용 부분) 제거

**검증**:
```bash
grep -n "tab_contacts\|tab_offers\|contact_create\|offer_create" projects/templates/projects/partials/detail_tab_bar.html projects/templates/projects/partials/tab_overview.html
```
→ 0건 또는 주석만 남음.

---

### T3b.11 — Placeholder 템플릿 생성
**작업**: 아래 파일들을 최소 placeholder로 생성. Phase 4에서 실제 UI 구현.

각 파일 내용 예시:
```html
{# Phase 3b placeholder — real UI in Phase 4 #}
<div class="p-4 text-gray-400 text-sm">
  [placeholder: {template_name}]
</div>
```

대상 파일 (신규 생성):
- `projects/templates/projects/partials/add_candidate_modal.html`
- `projects/templates/projects/partials/drop_application_modal.html`
- `projects/templates/projects/partials/application_card.html`
- `projects/templates/projects/partials/application_actions_list.html`
- `projects/templates/projects/partials/action_create_modal.html`
- `projects/templates/projects/partials/action_complete_modal.html`
- `projects/templates/projects/partials/action_propose_next_modal.html`
- `projects/templates/projects/partials/action_item_card.html`
- `projects/templates/projects/partials/action_skip_modal.html`
- `projects/templates/projects/partials/action_reschedule_modal.html`

---

### T3b.12 — `views.py` 잔여 Contact·Offer grep
**작업**:
```bash
grep -n "class Contact\b\|class Offer\b\|models\.Offer\b\|from .*import.*Offer\b\|from .*import.*Contact\b\|ContactForm\|OfferForm" projects/views.py
```
→ 결과 0건.

**주의**: `ProjectStatus`는 유효한 라이브 enum이므로 제거하지 않는다.

남아있으면 즉시 정리.

---

### T3b.13 — `python manage.py check` + 스모크 + 에러 경로 테스트
**작업**:
```bash
uv run python manage.py check
uv run python manage.py runserver 0.0.0.0:8000
```

**기본 스모크 확인** (curl 또는 pytest):
- `/projects/<id>/add_candidate/` GET → 200 (모달 폼)
- `/projects/<id>/add_candidate/` POST → Application 생성 (204 + HX-Trigger)
- `/applications/<id>/drop/` GET → 200 (모달 폼)
- `/applications/<id>/drop/` POST → 드롭 (200 + 카드 갱신)
- `/applications/<id>/hire/` POST → 입사 + 자동 종료 (204 + HX-Redirect)
- `/applications/<id>/actions/new/` GET → 200 (모달 폼)
- `/applications/<id>/actions/new/` POST → ActionItem 생성 (204 + HX-Trigger)

**에러 경로 확인**:
- 이미 드롭된 Application에 drop → 400
- 이미 입사한 Application에 hire → 409
- 종료된 프로젝트에 add_candidate → 400
- 중복 candidate 추가 → 400
- pending이 아닌 action에 complete/skip → 400
- 완료되지 않은 action에 propose_next → 400

**NoReverseMatch 확인**:
```bash
# 모든 프로젝트 상세 페이지 렌더링 시 {% url %} 에러 없음 확인
uv run python manage.py shell -c "
from django.test import Client
c = Client()
c.login(...)
# project detail 페이지 로드 → 500 없음 확인
"
```

(템플릿은 placeholder이므로 200 응답만 확인. 실제 UI는 Phase 4)

---

## 5. 검증 체크리스트

- [ ] `create_application` 서비스 함수 추가 (application_lifecycle.py)
- [ ] `project_add_candidate` 구현 (GET/POST, org scoping, error handling)
- [ ] `application_drop` 구현 (GET/POST, error handling, HX-Trigger)
- [ ] `application_restore` 구현 (POST, error handling, HX-Trigger)
- [ ] `application_hire` 구현 (POST, error handling, HX-Redirect)
- [ ] `application_actions_partial` 구현 (GET)
- [ ] `action_create` 구현 (GET/POST, consistent form, error handling)
- [ ] `action_complete` 구현 (GET/POST, propose_next, error handling)
- [ ] `action_skip` 구현 (GET/POST, error handling)
- [ ] `action_reschedule` 구현 (GET/POST, error handling)
- [ ] `action_propose_next` 구현 (POST, validation, atomic, error handling)
- [ ] `views_voice.py` 수정 완료
- [ ] `action_executor.py` legacy intent 비활성화
- [ ] `intent_parser.py` legacy intent 제거
- [ ] `offer_*`, `status_update`, `contact_*` 함수 전부 제거
- [ ] `project_tab_contacts`, `project_tab_offers` stub 교체
- [ ] `_DeletedModelSentinel` 제거
- [ ] `urls.py`에서 offer/status_update/contact CRUD 라우트 제거
- [ ] `detail_tab_bar.html` contacts/offers 탭 제거
- [ ] `tab_overview.html` contacts/offers 링크 제거
- [ ] Placeholder 템플릿 10개 생성
- [ ] `grep Contact projects/views.py` → 0건 (import 포함)
- [ ] `grep "Offer" projects/views.py` → 0건 (import 포함)
- [ ] `python manage.py check` 통과
- [ ] `runserver` 기동 + 주요 엔드포인트 정상 응답
- [ ] 에러 경로 테스트 (드롭/입사/완료 등 ValueError → 400/409)
- [ ] NoReverseMatch 없음 확인

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `views_voice.py` + voice 서비스에 의도된 동작이 모호 | 기존 voice 라우팅 코드 분석 후 Contact/Offer 기반 명령은 모두 제거. 새 명령 추가는 Phase 4 이후로 미룸 |
| `action_complete` 응답이 후속 제안 모달인데 Phase 4b 모달이 아직 없음 | placeholder 모달로 200 응답만 보장. 실제 UI는 Phase 4b |
| Permission 검사 | `@membership_required` + `_get_org(request)` 일관 사용. `request.user.organization` 직접 접근 금지 |
| `require_POST` 데코레이터로 GET 요청 405 | 모달이 필요한 view는 GET/POST 분기. restore/hire/propose_next는 POST only 유지 |
| 후보자 검색 모달 API 없음 (`add_candidate_modal`) | Phase 4b에서 검색 결과 partial 추가. Phase 3b는 form select 기본 위젯으로 충분 |
| legacy tab 제거 시 기존 북마크/링크 깨짐 | tab URL은 유지하되 stub 응답 반환. CRUD URL만 제거 |
| Lifecycle service ValueError가 500으로 노출 | 모든 서비스 호출에 try/except ValueError 필수 |
| race condition: 동시 hire/drop | 서비스 레이어의 select_for_update + atomic이 처리. View는 IntegrityError/ValueError만 catch |
| action_propose_next 부분 생성 | transaction.atomic()으로 all-or-nothing. 사전 검증으로 실패 방지 |

## 7. 커밋 포인트

```
feat(projects): implement Application/ActionItem CRUD views + remove legacy

- Add create_application service with closed-project guard + atomic creation
- Implement project_add_candidate with org scoping + error handling (GET/POST)
- Implement application_drop/restore/hire with lifecycle error handling
- Implement action_create/complete/skip/reschedule with GET modal + POST mutation
- Implement action_propose_next with validation + atomic batch creation
- All HTMX endpoints use HX-Trigger/HX-Redirect instead of Django redirect
- Disable legacy voice intents (contact_record, contact_reserve, offer_create)
- Remove offer_*, status_update, contact_* views and URL routes
- Stub project_tab_contacts/offers, update tab bar + overview templates
- Remove _DeletedModelSentinel classes
- Create 10 placeholder partial templates for Phase 4
- views.py free of Contact/Offer references (ProjectStatus retained as live enum)

Refs: FINAL-SPEC.md §5
```

## 8. Phase 4a로 넘기는 인터페이스

- 모든 뷰가 동작 (placeholder 템플릿이지만 200/204/400 응답 일관)
- HTMX 계약 정의됨: 각 view의 docstring에 GET/POST 동작, HX-Trigger 이벤트 명시
- 템플릿 경로가 모두 확정됨 (10개 placeholder + 기존 partials)
- Phase 4a는 이 템플릿 파일들을 실제 UI로 채우는 작업
- HX-Trigger 이벤트: `applicationChanged`, `actionChanged` — Phase 4 템플릿이 `hx-trigger="... from:body"`로 구독

---

**이전 Phase**: [phase-3a-views-base.md](phase-3a-views-base.md)
**다음 Phase**: [phase-4a-templates-core.md](phase-4a-templates-core.md)

<!-- forge:phase-3b-views-crud:impl-plan:complete:2026-04-14T10:26:12Z -->
