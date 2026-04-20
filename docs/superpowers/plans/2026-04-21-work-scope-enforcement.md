# 업무 스코프 일관 적용 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업무 모델(Project/Application/ActionItem/Interview/Submission) 뷰 전반에 Level 기반 스코프를 일관 적용하고, 단일테넌트 리팩터 잔재(삭제된 `organization` FK·데드 파라미터)를 청소한다.

**Architecture:** `accounts/services/scope.py` 에 모델별 scope 규칙 맵 + `get_scoped_object_or_404` 헬퍼를 추가한다. 기존 `scope_work_qs(qs, user)` 는 맵 기반으로 재구현. `projects/views.py` 외 업무 뷰들의 `get_object_or_404(WorkModel, ...)` 호출을 새 헬퍼로 일괄 치환. Level 1 직원이 남의 업무 pk 로 접근하면 `Http404` 를 돌려 존재 자체를 은닉한다.

**Tech Stack:** Django 5.2 ORM · pytest-django · `accounts.services.scope`.

**Spec:** `docs/superpowers/specs/2026-04-21-work-scope-enforcement-design.md`

---

## File Structure

### 수정 파일

| 경로 | 변경 요약 |
|---|---|
| `accounts/services/scope.py` | 모델별 규칙 맵 `_WORK_SCOPE_RULES` + `get_scoped_object_or_404` 추가. `scope_work_qs` 시그니처 `(qs, user)` 2인자로 단순화 + 맵 기반 내부화 |
| `tests/accounts/test_scope_work_qs.py` | Application/ActionItem/Interview/Submission 케이스 추가 |
| `tests/accounts/test_scoped_object.py` | **신규** — `get_scoped_object_or_404` 단위 테스트 |
| `projects/services/dashboard.py` | `scope_owner` 플래그 제거, 내부 쿼리를 `scope_work_qs` 로 통일. `_scope_projects(user)` 로 시그니처 단순화. `get_dashboard_context` 의 TODO 주석 삭제 |
| `projects/views.py` | `get_object_or_404(Project/Application/ActionItem/Interview/Submission, ...)` 를 `get_scoped_object_or_404(...)` 로 전수 치환 |
| `projects/views_voice.py` | 동일 패턴 치환 |
| `projects/views_telegram.py` | 동일 패턴 치환 |
| `tests/test_work_scope_404.py` | **신규** — cross-user 404 통합 테스트 |
| `projects/management/commands/close_overdue_projects.py` | `.select_related("organization", "client")` → `.select_related("client")` |
| `clients/services/client_queries.py` | `org=None` 파라미터 및 `organization=org` 필터 제거 + 호출처 동반 수정 |
| `projects/services/voice/action_executor.py` | `organization=None` 파라미터 전수 제거 |
| `projects/services/voice/context_resolver.py` | 동일 |
| `projects/services/voice/entity_resolver.py` | 동일 |
| `projects/services/candidate_matching.py` | 동일 |
| `candidates/views_extension.py` | 응답의 `"organization": None` 필드 제거 |
| `tests/test_extension_api.py` | organization 검증 assertion 삭제 |
| `conftest.py`, `tests/conftest.py`, `main/urls.py` | stale 주석 `membership`/`organization` 언급 정리 |

### 신규 파일

| 경로 | 책임 |
|---|---|
| `tests/accounts/test_scoped_object.py` | `get_scoped_object_or_404` 단위 테스트 |
| `tests/test_work_scope_404.py` | cross-user 403→404 통합 테스트 |

---

## Key Codebase Facts (엔지니어 먼저 읽어둘 것)

- **권한 모델:** `User.level` 0=대기, 1=직원, 2=사장. `is_superuser` 는 개발자. 게이트는 `accounts/decorators.py:level_required(n)`.
- **기존 헬퍼:** `accounts/services/scope.py::scope_work_qs(qs, user, assigned_field="assigned_consultants")` — **현재 쿼리셋 필터 용도**. `assigned_field` 키워드는 Project 용으로만 쓰임. Task 1에서 `(qs, user)` 2인자로 단순화.
- **업무 모델 위치:** 전부 `projects/models.py` — `Project`(line 159), `Application`(331), `ActionItem`(561), `Submission`(651), `Interview`(784).
- **Foreign key chain (전부 `on_delete=models.CASCADE`):**
  - `Application.project` → Project
  - `ActionItem.application` → Application
  - `Submission.application` → Application (OneToOne)
  - `Interview.action_item` → ActionItem (OneToOne)
- **Project.assigned_consultants** 은 `User` M2M.
- **ActionItem.assigned_to** 은 `User` FK (nullable).
- **기존 pytest fixtures** (`tests/conftest.py`): `pending_user`, `staff_user`, `staff_user_2`, `boss_user`, `dev_user`, 각각의 `_client`. `client_company`, `project`(boss 가 생성), `project_assigned_to_staff`, `candidate`, `application`.
- **URL 구조 예:** `/projects/<uuid:pk>/`, `/projects/<uuid:pk>/submissions/<uuid:sub_pk>/`. view name 은 `accounts/urls.py`/`projects/urls.py` 참조.
- **기존 `_scope_projects`** (`projects/services/dashboard.py:446`): 인자 `(user, scope_owner)`. Task 2에서 `scope_owner` 제거.

---

## Task 1: `get_scoped_object_or_404` + 규칙 맵

**Files:**
- Modify: `accounts/services/scope.py`
- Test: `tests/accounts/test_scope_work_qs.py`
- Create: `tests/accounts/test_scoped_object.py`

- [ ] **Step 1: 규칙 맵 실패 테스트 추가**

`tests/accounts/test_scope_work_qs.py` 맨 뒤에 추가:

```python
import pytest
from django.db.models import Q


@pytest.mark.django_db
def test_application_scope_for_staff(staff_user, project_assigned_to_staff, candidate):
    from projects.models import Application
    from accounts.services.scope import scope_work_qs

    app_own = Application.objects.create(
        project=project_assigned_to_staff, candidate=candidate, created_by=staff_user
    )
    qs = scope_work_qs(Application.objects.all(), staff_user)
    ids = set(qs.values_list("id", flat=True))
    assert app_own.id in ids


@pytest.mark.django_db
def test_action_item_scope_or_rule(staff_user, staff_user_2, project, candidate):
    """ActionItem: 본인 assigned_to 거나 본인이 컨설턴트인 프로젝트의 액션."""
    from projects.models import Application, ActionItem, ActionType
    from accounts.services.scope import scope_work_qs

    project.assigned_consultants.add(staff_user_2)
    app = Application.objects.create(
        project=project, candidate=candidate, created_by=staff_user_2
    )
    atype, _ = ActionType.objects.get_or_create(
        code="test_action", defaults={"label": "테스트"}
    )

    ai_own = ActionItem.objects.create(
        application=app, action_type=atype, title="내 TODO", assigned_to=staff_user
    )
    ai_project = ActionItem.objects.create(
        application=app, action_type=atype, title="팀원 TODO",
        assigned_to=staff_user_2,
    )

    qs = scope_work_qs(ActionItem.objects.all(), staff_user)
    ids = set(qs.values_list("id", flat=True))
    assert ai_own.id in ids
    assert ai_project.id not in ids


@pytest.mark.django_db
def test_unknown_model_raises(staff_user):
    from clients.models import Client
    from accounts.services.scope import scope_work_qs

    with pytest.raises(ValueError):
        scope_work_qs(Client.objects.all(), staff_user)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/accounts/test_scope_work_qs.py -v`
Expected: 위 3개 테스트 모두 FAIL (ValueError 아직 없음, Application 스코프 구현 안 됨)

- [ ] **Step 3: `accounts/services/scope.py` 전면 교체**

파일 전체를 아래 내용으로 덮어쓴다:

```python
"""Query scope helpers for work-type entities.

Work entities: Project, Application, ActionItem, Interview, Submission.
Info entities (Candidate, Client, references) bypass scope — gated only by
`accounts.decorators.level_required(1)`.

Level 2+ / is_superuser: full access.
Level 1 (staff): limited to assigned/own records per _WORK_SCOPE_RULES.
Level 0 (pending): empty.
"""

from django.db.models import Q
from django.http import Http404


def _project_rule(user):
    return Q(assigned_consultants=user)


def _application_rule(user):
    return Q(project__assigned_consultants=user)


def _action_item_rule(user):
    return Q(assigned_to=user) | Q(
        application__project__assigned_consultants=user
    )


def _interview_rule(user):
    return Q(action_item__application__project__assigned_consultants=user)


def _submission_rule(user):
    return Q(application__project__assigned_consultants=user)


def _build_rules():
    from projects.models import (
        ActionItem,
        Application,
        Interview,
        Project,
        Submission,
    )

    return {
        Project: _project_rule,
        Application: _application_rule,
        ActionItem: _action_item_rule,
        Interview: _interview_rule,
        Submission: _submission_rule,
    }


_WORK_SCOPE_RULES = None


def _rule_for(model):
    global _WORK_SCOPE_RULES
    if _WORK_SCOPE_RULES is None:
        _WORK_SCOPE_RULES = _build_rules()
    rule = _WORK_SCOPE_RULES.get(model)
    if rule is None:
        raise ValueError(
            f"No work-scope rule for {model.__name__}. "
            f"Add one in accounts/services/scope.py::_build_rules."
        )
    return rule


def scope_work_qs(qs, user):
    """Filter a work-entity queryset by the user's permission level.

    - Level 0 (pending): empty queryset.
    - Level 1 (staff): filtered to assigned/own per model rule.
    - Level 2+ or is_superuser: full queryset.
    """
    if user.is_superuser or user.level >= 2:
        return qs
    if user.level < 1:
        return qs.none()
    rule = _rule_for(qs.model)
    return qs.filter(rule(user)).distinct()


def get_scoped_object_or_404(model, user, **lookup):
    """Fetch a work-model instance subject to the user's scope.

    Level 2+ / superuser: behaves like django.shortcuts.get_object_or_404.
    Level 1: raises Http404 if the user is not assigned to the object.
    Level 0: always Http404.
    """
    qs = scope_work_qs(model.objects.all(), user)
    try:
        return qs.get(**lookup)
    except model.DoesNotExist:
        raise Http404(f"{model.__name__} matching query does not exist.")
```

- [ ] **Step 4: 테스트 실행 — Task 1 추가분 확인**

Run: `uv run pytest tests/accounts/test_scope_work_qs.py -v`
Expected: 모두 PASS (기존 4개 + 신규 3개)

- [ ] **Step 5: `get_scoped_object_or_404` 테스트 파일 생성**

`tests/accounts/test_scoped_object.py` 신규 작성:

```python
import pytest
from django.http import Http404

from accounts.services.scope import get_scoped_object_or_404
from projects.models import Project


@pytest.mark.django_db
def test_boss_gets_any_project(boss_user, project):
    result = get_scoped_object_or_404(Project, boss_user, pk=project.pk)
    assert result.pk == project.pk


@pytest.mark.django_db
def test_superuser_gets_any_project(dev_user, project):
    result = get_scoped_object_or_404(Project, dev_user, pk=project.pk)
    assert result.pk == project.pk


@pytest.mark.django_db
def test_staff_gets_own_project(staff_user, project_assigned_to_staff):
    result = get_scoped_object_or_404(
        Project, staff_user, pk=project_assigned_to_staff.pk
    )
    assert result.pk == project_assigned_to_staff.pk


@pytest.mark.django_db
def test_staff_denied_others_project(staff_user, project):
    """project is assigned to boss_user, not staff_user → 404."""
    with pytest.raises(Http404):
        get_scoped_object_or_404(Project, staff_user, pk=project.pk)


@pytest.mark.django_db
def test_pending_denied(pending_user, project):
    with pytest.raises(Http404):
        get_scoped_object_or_404(Project, pending_user, pk=project.pk)


@pytest.mark.django_db
def test_missing_pk_is_404(boss_user, db):
    import uuid
    with pytest.raises(Http404):
        get_scoped_object_or_404(Project, boss_user, pk=uuid.uuid4())
```

- [ ] **Step 6: 테스트 실행**

Run: `uv run pytest tests/accounts/test_scoped_object.py -v`
Expected: 6개 모두 PASS

- [ ] **Step 7: 호출처 비호환 사이드이펙트 확인**

`scope_work_qs` 의 세 번째 인자 `assigned_field` 를 지웠으므로 사용처 확인:

Run: `uv run grep -rn "scope_work_qs(.*assigned_field" --include='*.py' .`
Expected: 결과 없음 (Task 1 전에는 zero 여야 한다. 만약 결과가 나오면 해당 호출을 모두 수정).

- [ ] **Step 8: 커밋**

```bash
git add accounts/services/scope.py tests/accounts/test_scope_work_qs.py tests/accounts/test_scoped_object.py
git commit -m "$(cat <<'EOF'
refactor(scope): add model-aware work-scope rules + get_scoped_object_or_404

scope_work_qs is now a single (qs, user) function that looks up a
per-model rule from _WORK_SCOPE_RULES. get_scoped_object_or_404 wraps
the same filtering for single-object fetches used by views.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Dashboard service 를 `scope_work_qs` 로 통합

**Files:**
- Modify: `projects/services/dashboard.py`
- Test: `tests/test_dashboard_phase2a.py`, `tests/test_views_dashboard.py`

- [ ] **Step 1: 회귀 기준 확인**

Run: `uv run pytest tests/test_dashboard_phase2a.py tests/test_views_dashboard.py -q`
Expected: 17 passed

- [ ] **Step 2: `_scope_projects` 를 1인자로 단순화**

`projects/services/dashboard.py:446-451` 교체:

```python
def _scope_projects(user):
    """업무 스코프 쿼리셋. scope_work_qs 를 그대로 사용."""
    from accounts.services.scope import scope_work_qs
    return scope_work_qs(Project.objects.all(), user)
```

- [ ] **Step 3: `_monthly_success` / `_project_status_counts` scope_owner 제거**

`projects/services/dashboard.py:185-217` 를 아래로 교체:

```python
def _monthly_success(user):
    """S1-1 Monthly Success: 이번 달 성공·진행중·성공률."""
    now_local = timezone.localtime()
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = _scope_projects(user)

    closed_this_month = qs.filter(
        status=ProjectStatus.CLOSED,
        closed_at__gte=month_start,
    )
    success = closed_this_month.filter(result=ProjectResult.SUCCESS).count()
    fail = closed_this_month.filter(result=ProjectResult.FAIL).count()
    active = qs.filter(status=ProjectStatus.OPEN).count()
    total = success + fail
    return {
        "success_count": success,
        "active_count": active,
        "success_rate": round(success / total * 100) if total else None,
    }


def _project_status_counts(user):
    """S1-3 Project Status: searching/screening/closed 누적 개수."""
    qs = _scope_projects(user)
    return {
        "searching": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SEARCHING
        ).count(),
        "screening": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SCREENING
        ).count(),
        "closed": qs.filter(status=ProjectStatus.CLOSED).count(),
    }
```

- [ ] **Step 4: `_weekly_schedule` 에 `scope_work_qs` 적용**

`projects/services/dashboard.py:288-339` 내부에서 `scope_owner` 분기 (line 311) 를 `scope_work_qs` 로 교체. 함수 시그니처도 변경.

교체 내용:

```python
def _weekly_schedule(user, limit: int = 5):
    """S3 Weekly Schedule: 이번 주 Interview + ActionItem 합집합, 시간 asc."""
    from accounts.services.scope import scope_work_qs

    monday, next_monday = _week_range()

    interviews = scope_work_qs(
        Interview.objects.filter(
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        ),
        user,
    ).select_related(
        "action_item__application__candidate",
        "action_item__application__project__client",
    )
    actions = scope_work_qs(
        ActionItem.objects.filter(
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        )
        .exclude(action_type__code="interview_round"),
        user,
    ).select_related(
        "action_type",
        "application__project__client",
    )

    events = []

    for iv in interviews:
        candidate = iv.action_item.application.candidate
        events.append({
            "scheduled_at": iv.scheduled_at,
            "label_color": "info",
            "title": f"{iv.round}차 면접",
            "subtitle": f"후보자: {candidate.name} · {iv.location or '-'}",
        })

    for ai in actions:
        code = ai.action_type.code
        color = "warning" if code in _CLIENT_FACING_CODES else "ink3"
        proj = ai.application.project
        client = proj.client
        events.append({
            "scheduled_at": ai.scheduled_at,
            "label_color": color,
            "title": ai.title,
            "subtitle": f"{proj.title} · {client.name}",
        })

    events.sort(key=lambda e: e["scheduled_at"])
    return events[:limit]
```

**주의:** 기존 `_weekly_schedule` 본문의 나머지 (events 루프, sort, slice) 는 유지. 만약 원본 끝부분이 이 샘플과 다르면 diff 로 확인 후 scope 적용 블록만 교체.

- [ ] **Step 5: `_monthly_calendar` 시그니처 변경**

`projects/services/dashboard.py:353` 함수 `_monthly_calendar(user, scope_owner)` 를 `_monthly_calendar(user)` 로 바꾸고, 내부 `if not scope_owner:` 분기를 `scope_work_qs` 호출로 교체.

원본 blocks (line 379, 395 부근) 확인:

```python
if not scope_owner:
    <필터링>
```

이걸 제거하고, 상위의 `Interview.objects.filter(...)` / `ActionItem.objects.filter(...)` 를 `scope_work_qs(Interview.objects.filter(...), user)` 로 래핑.

구체적으로, `_monthly_calendar` 원본을 다음 형태로 수정 (실제 파일에서 line 번호 변화에 주의):

```python
def _monthly_calendar(user) -> list[dict]:
    """S3 Monthly Calendar: 이번 달 이벤트 리스트."""
    from accounts.services.scope import scope_work_qs

    now_local = timezone.localtime()
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start + timedelta(days=32)).replace(day=1)

    interviews = scope_work_qs(
        Interview.objects.filter(
            scheduled_at__gte=month_start,
            scheduled_at__lt=next_month,
        ),
        user,
    ).select_related("action_item__application__project")

    actions = scope_work_qs(
        ActionItem.objects.filter(
            scheduled_at__gte=month_start,
            scheduled_at__lt=next_month,
        ),
        user,
    ).select_related("application__project", "action_type")

    cells = []
    for iv in interviews:
        cells.append({
            "date": iv.scheduled_at.date().isoformat(),
            "event_label": f"{iv.round}차 면접",
        })
    for ai in actions:
        cells.append({
            "date": ai.scheduled_at.date().isoformat(),
            "event_label": ai.title,
        })
    return cells
```

원본 `_monthly_calendar` 의 출력 모양이 다르면 본 수정은 scope 적용 블록만 교체하고 나머지 로직은 그대로 둘 것.

- [ ] **Step 6: `get_dashboard_context` 간소화**

`projects/services/dashboard.py:425-443` 교체:

```python
def get_dashboard_context(user: User) -> dict:
    """대시보드 카드 전체 컨텍스트.

    Phase 2a: S1-1 Monthly Success, S1-3 Project Status,
              S2-1 Team Performance, S3 Weekly/Monthly Calendar.
    Phase 2b 카드(S1-2 Revenue, S2-2 Recent Activity)는 하드코딩 유지.
    """
    return {
        "monthly_success": _monthly_success(user),
        "project_status": _project_status_counts(user),
        "team_performance": _team_performance(),
        "weekly_schedule": _weekly_schedule(user),
        "monthly_calendar": _monthly_calendar(user),
        "_scope_owner": user.is_superuser or user.level >= 2,
    }
```

- [ ] **Step 7: 회귀 테스트**

Run: `uv run pytest tests/test_dashboard_phase2a.py tests/test_views_dashboard.py -q`
Expected: 17 passed

- [ ] **Step 8: 커밋**

```bash
git add projects/services/dashboard.py
git commit -m "$(cat <<'EOF'
refactor(dashboard): use scope_work_qs for internal queries

_scope_projects and the weekly/monthly aggregators now defer entirely
to scope_work_qs. Drops the scope_owner boolean plumbed through helpers
and resolves the T10 TODO in get_dashboard_context.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `projects/views.py` Project 뷰 치환

**Files:**
- Modify: `projects/views.py`

- [ ] **Step 1: 기준 건수 측정**

Run: `uv run grep -cn "get_object_or_404(Project" projects/views.py`
Expected: 52 (±몇 건. 실제 숫자를 기록해 두면 Step 4에서 0 이어야 한다).

- [ ] **Step 2: import 추가**

`projects/views.py:20` 위치 (기존 `from accounts.services.scope import scope_work_qs`) 를 교체:

```python
from accounts.services.scope import get_scoped_object_or_404, scope_work_qs
```

- [ ] **Step 3: Project 조회 치환**

`projects/views.py` 전체에서 다음 패턴 전수 치환:

```python
# Before
project = get_object_or_404(Project, pk=pk)

# After
project = get_scoped_object_or_404(Project, request.user, pk=pk)
```

그리고:

```python
# Before (line 2453 같은 별칭 pk)
project = get_object_or_404(Project, pk=project_pk)

# After
project = get_scoped_object_or_404(Project, request.user, pk=project_pk)
```

편집 도구로 `get_object_or_404(Project, ` → `get_scoped_object_or_404(Project, request.user, ` 전역 치환 가능. 다만 `request` 가 함수 인자명이 아닌 케이스가 혹시 있는지 Step 4에서 검증.

- [ ] **Step 4: 치환 완전성 검증**

Run: `uv run grep -cn "get_object_or_404(Project" projects/views.py`
Expected: 0

Run: `uv run grep -n "get_scoped_object_or_404(Project" projects/views.py | wc -l`
Expected: Step 1의 기준 건수와 동일.

- [ ] **Step 5: syntax·import 점검**

Run: `uv run python -c "import projects.views"`
Expected: 무출력 (성공).

- [ ] **Step 6: 기존 테스트 회귀**

Run: `uv run pytest projects/ tests/ -q -x --ignore=tests/test_work_scope_404.py`
Expected: 973 passed (기존 카운트와 동일). 실패 나면 해당 테스트 조사 후 Task 1~2 의 기존 퍼미션 가정이 깨졌는지 확인.

- [ ] **Step 7: 커밋**

```bash
git add projects/views.py
git commit -m "$(cat <<'EOF'
refactor(projects): use get_scoped_object_or_404 for Project lookups

All direct get_object_or_404(Project, ...) calls in projects/views.py
now go through the scope helper. Level-1 staff who request a project
they are not assigned to receive 404 instead of the full detail.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `projects/views.py` Application/ActionItem/Interview/Submission 치환

**Files:**
- Modify: `projects/views.py`

- [ ] **Step 1: 기준 건수 측정**

Run:
```bash
uv run grep -cn "get_object_or_404(Application" projects/views.py
uv run grep -cn "get_object_or_404(ActionItem" projects/views.py
uv run grep -cn "get_object_or_404(Interview" projects/views.py
uv run grep -cn "get_object_or_404(Submission" projects/views.py
```
각 건수 기록.

- [ ] **Step 2: Application 치환**

```python
# Before
app = get_object_or_404(Application, pk=pk)

# After
app = get_scoped_object_or_404(Application, request.user, pk=pk)
```

- [ ] **Step 3: ActionItem 치환**

```python
# Before
item = get_object_or_404(ActionItem, pk=...)

# After
item = get_scoped_object_or_404(ActionItem, request.user, pk=...)
```

- [ ] **Step 4: Interview 치환**

```python
# Before
interview = get_object_or_404(Interview, pk=...)

# After
interview = get_scoped_object_or_404(Interview, request.user, pk=...)
```

- [ ] **Step 5: Submission 치환 (상위 project 체크 제거)**

`projects/views.py:1079-1229` 부근의 패턴:

```python
# Before
project = get_scoped_object_or_404(Project, request.user, pk=pk)  # Task 3에서 이미 적용됨
submission = get_object_or_404(Submission, pk=sub_pk, project=project)
```

다음으로 치환:

```python
# After
project = get_scoped_object_or_404(Project, request.user, pk=pk)
submission = get_scoped_object_or_404(Submission, request.user, pk=sub_pk, application__project=project)
```

**주의:** `Submission` 모델은 `application` FK 를 가지므로 `project=` 필터는 `application__project=` 로 바꿔야 한다. 기존 필터가 `project=project` 였으므로 무조건 바꿔야 필드 에러를 피한다. 이 과정에서 기존 코드가 `Submission.project` 가 아니라 `Submission.application.project` 였는지 확인:

Run: `uv run grep -n "^\s\+project = models" projects/models.py | head`
그리고 `Submission` 클래스 영역(line 651~)을 조사해 `project` 필드가 직접 있는지 확인. 직접 없으면 위 수정이 맞음; 있으면 기존 `project=project` 유지하되 `get_scoped_object_or_404(Submission, request.user, pk=sub_pk, project=project)`.

- [ ] **Step 6: 치환 완전성 검증**

Run:
```bash
uv run grep -cn "get_object_or_404(Application" projects/views.py
uv run grep -cn "get_object_or_404(ActionItem" projects/views.py
uv run grep -cn "get_object_or_404(Interview" projects/views.py
uv run grep -cn "get_object_or_404(Submission" projects/views.py
```
Expected: 모두 0.

- [ ] **Step 7: syntax·import 점검**

Run: `uv run python -c "import projects.views"`
Expected: 무출력.

- [ ] **Step 8: 기존 테스트 회귀**

Run: `uv run pytest projects/ tests/ -q -x --ignore=tests/test_work_scope_404.py`
Expected: 973 passed.

- [ ] **Step 9: 커밋**

```bash
git add projects/views.py
git commit -m "$(cat <<'EOF'
refactor(projects): scope Application/ActionItem/Interview/Submission lookups

Extends Task 3 to the remaining work-model fetches in projects/views.py.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `views_voice.py` + `views_telegram.py` 치환

**Files:**
- Modify: `projects/views_voice.py`
- Modify: `projects/views_telegram.py`

- [ ] **Step 1: 두 파일에서 업무 모델 조회 위치 확인**

Run:
```bash
uv run grep -n "get_object_or_404(Project\|get_object_or_404(Application\|get_object_or_404(ActionItem\|get_object_or_404(Interview\|get_object_or_404(Submission" projects/views_voice.py projects/views_telegram.py
```
출력된 라인을 전부 기록.

- [ ] **Step 2: import 보강**

두 파일 각각 상단 import 블록에 추가:

```python
from accounts.services.scope import get_scoped_object_or_404
```

(이미 있으면 skip.)

- [ ] **Step 3: Project 조회 치환**

각 출력 라인의 `get_object_or_404(Project, ...)` → `get_scoped_object_or_404(Project, request.user, ...)`.

**주의:** telegram webhook 뷰는 `request.user` 가 anonymous 일 수 있다. `@level_required(1)` 이 안 붙은 엔드포인트는 스코프 적용 대상이 아님. Step 1 에서 찾은 각 뷰 함수 상단에 `@level_required` 데코레이터가 있는지 확인하고, **없는 뷰는 치환하지 않는다** (webhook 은 `projects/telegram/auth.py` 의 자체 chat_id 인증으로 이미 handled).

- [ ] **Step 4: Application/ActionItem 등 치환**

같은 원칙. 데코레이터 게이트 없는 뷰는 제외.

- [ ] **Step 5: 완전성 검증**

Run:
```bash
uv run grep -n "get_object_or_404(Project\|get_object_or_404(Application\|get_object_or_404(ActionItem\|get_object_or_404(Interview\|get_object_or_404(Submission" projects/views_voice.py projects/views_telegram.py
```
Expected: 오직 웹훅 뷰 내부 (데코레이터 없음) 만 남음. 데코레이터 붙은 뷰는 전부 치환.

- [ ] **Step 6: syntax 체크**

Run: `uv run python -c "import projects.views_voice; import projects.views_telegram"`
Expected: 무출력.

- [ ] **Step 7: 회귀 테스트**

Run: `uv run pytest -q -x --ignore=tests/test_work_scope_404.py`
Expected: 973 passed.

- [ ] **Step 8: 커밋**

```bash
git add projects/views_voice.py projects/views_telegram.py
git commit -m "$(cat <<'EOF'
refactor(projects): scope work-model lookups in voice/telegram views

Auth-gated (level_required) views now use get_scoped_object_or_404.
Telegram webhook endpoints are left untouched — they authenticate via
chat_id binding, not the user session.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: cross-user 404 통합 테스트

**Files:**
- Create: `tests/test_work_scope_404.py`

- [ ] **Step 1: 테스트 파일 생성**

```python
"""Cross-user 404 integration — Level 1 staff cannot access other staff's work.

This file is the executable contract for the scope enforcement spec
(docs/superpowers/specs/2026-04-21-work-scope-enforcement-design.md).
"""
import pytest


@pytest.fixture
def other_project(db, client_company, staff_user_2):
    from projects.models import Project, ProjectStatus
    p = Project.objects.create(
        client=client_company, title="남의 것", status=ProjectStatus.OPEN,
        created_by=staff_user_2,
    )
    p.assigned_consultants.add(staff_user_2)
    return p


@pytest.mark.django_db
def test_staff_gets_404_on_other_project_detail(staff_client, other_project):
    resp = staff_client.get(f"/projects/{other_project.pk}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_gets_404_on_other_project_applications_partial(staff_client, other_project):
    resp = staff_client.get(f"/projects/{other_project.pk}/applications/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_gets_404_on_other_project_timeline(staff_client, other_project):
    resp = staff_client.get(f"/projects/{other_project.pk}/timeline/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_gets_404_on_other_application(staff_client, other_project, candidate):
    from projects.models import Application
    app = Application.objects.create(
        project=other_project, candidate=candidate, created_by=other_project.created_by
    )
    # 실제 Application detail URL 패턴에 맞춰 경로 조정 필요. 실패시 urls.py 에서
    # name='application_detail' 등을 찾아 reverse 하라.
    from django.urls import reverse
    try:
        url = reverse("application_detail", kwargs={"pk": app.pk})
    except Exception:
        pytest.skip("application detail URL not present")
    resp = staff_client.get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_boss_sees_other_staff_project(boss_client, other_project):
    resp = boss_client.get(f"/projects/{other_project.pk}/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_superuser_sees_other_staff_project(dev_client, other_project):
    resp = dev_client.get(f"/projects/{other_project.pk}/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_staff_sees_own_project(staff_client, project_assigned_to_staff):
    resp = staff_client.get(f"/projects/{project_assigned_to_staff.pk}/")
    assert resp.status_code == 200
```

- [ ] **Step 2: URL 경로 검증**

위 테스트가 하드코딩한 `/projects/{pk}/applications/`, `/projects/{pk}/timeline/` 경로가 실제와 맞는지 확인:

Run: `uv run python manage.py show_urls 2>/dev/null | grep -E "projects/<uuid:pk>/(applications|timeline)" | head`

안 맞으면 실제 URL 로 정정. `show_urls` 가 없으면 `projects/urls.py` 를 읽어 `applications_partial` 또는 `project_applications_partial` 이름의 라우트 확인.

- [ ] **Step 3: 테스트 실행**

Run: `uv run pytest tests/test_work_scope_404.py -v`
Expected: 모두 PASS. 실패 시 해당 뷰가 Task 3/4에서 누락됐음을 뜻함 → 뷰 함수 역추적 후 치환.

- [ ] **Step 4: 커밋**

```bash
git add tests/test_work_scope_404.py
git commit -m "$(cat <<'EOF'
test: cross-user 404 integration for work-scope enforcement

Exercises the executable contract from the scope design: staff hitting
another staff's project/application URL gets 404, boss and superuser
get 200, and a staff member's own project is still accessible.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: B — 삭제된 `organization` FK 참조 제거

**Files:**
- Modify: `projects/management/commands/close_overdue_projects.py`
- Modify: `clients/services/client_queries.py`

- [ ] **Step 1: `close_overdue_projects.py` 수정**

`projects/management/commands/close_overdue_projects.py:45` 의

```python
.select_related("organization", "client")
```

을

```python
.select_related("client")
```

로 교체.

- [ ] **Step 2: 배치 커맨드 smoke**

Run: `uv run python manage.py close_overdue_projects --dry-run` (만약 `--dry-run` 옵션이 없으면 그냥 `close_overdue_projects`)
Expected: 런타임 에러 없이 "마감 경과 OPEN 프로젝트 없음." 또는 카운트 출력.

`--dry-run` 옵션이 없으면 dev DB 에서 실제 실행 가능 (더미 데이터, 사이드이펙트 없음).

- [ ] **Step 3: `client_queries.py` 수정 — 함수 시그니처**

`clients/services/client_queries.py` 파일 안의 `list_clients_with_stats(org=None, *, ...)` 및 같은 파일 내 다른 함수들에서 `org=None` 첫 파라미터를 제거. 본문의 `Client.objects.filter(organization=org) if org is not None else Client.objects.all()` 를 `Client.objects.all()` 로 교체.

예시 (line 17~26 부분):

```python
# Before
def list_clients_with_stats(
    org=None,
    *,
    categories=None,
    ...
):
    base = Client.objects.filter(organization=org) if org is not None else Client.objects.all()

# After
def list_clients_with_stats(
    *,
    categories=None,
    ...
):
    base = Client.objects.all()
```

그리고 line 91, 107 부근에도 동일 패턴 있으므로 같은 방식으로 수정.

- [ ] **Step 4: 호출처 수정**

Run: `uv run grep -rn "list_clients_with_stats\|list_clients\|client_queries\." --include='*.py' .`

각 호출처에서 `org=...` 포지셔널·키워드 인자 제거.

- [ ] **Step 5: 회귀 테스트**

Run: `uv run pytest tests/ clients/ -q -x`
Expected: 모두 PASS.

- [ ] **Step 6: 커밋**

```bash
git add projects/management/commands/close_overdue_projects.py clients/services/client_queries.py
git commit -m "$(cat <<'EOF'
fix(clients,projects): drop references to removed organization FK

close_overdue_projects and client_queries still joined on Project.organization
and Client.organization, both of which were dropped in the single-tenant
refactor (T6). Calling either would raise at runtime.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: C — 데드 `organization` 파라미터·응답 청소

**Files:**
- Modify: `projects/services/voice/action_executor.py`
- Modify: `projects/services/voice/context_resolver.py`
- Modify: `projects/services/voice/entity_resolver.py`
- Modify: `projects/services/candidate_matching.py`
- Modify: `candidates/views_extension.py`
- Modify: `tests/test_extension_api.py`
- Modify: `conftest.py`, `tests/conftest.py`, `main/urls.py`

- [ ] **Step 1: voice/* 파라미터 제거**

`projects/services/voice/action_executor.py` 의 모든 함수 시그니처에서 `organization=None` 제거. 함수 내부 `organization` 변수 사용처도 삭제.

Run: `uv run grep -n "organization" projects/services/voice/action_executor.py`
Expected (Step 1 후): 결과 없음.

동일 작업을 `context_resolver.py`, `entity_resolver.py` 에도 반복.

Run: `uv run grep -n "organization" projects/services/voice/`
Expected: 결과 없음.

- [ ] **Step 2: candidate_matching 파라미터 제거**

`projects/services/candidate_matching.py` 의 `organization=None` 파라미터와 관련 주석 제거.

Run: `uv run grep -n "organization" projects/services/candidate_matching.py`
Expected: 결과 없음.

- [ ] **Step 3: 호출처 일괄 수정**

위 4개 파일을 부르는 코드에서 `organization=...` 인자 제거:

Run: `uv run grep -rn "organization=" --include='*.py' projects/ tests/`
출력된 각 호출처를 수정.

- [ ] **Step 4: extension API 응답 정리**

`candidates/views_extension.py:74` 의 `"organization": None,` 라인 삭제.

`tests/test_extension_api.py` 의 다음 라인 삭제:
- `self.assertIsNone(body["data"]["organization"])` (line 85, 94)
- `def test_no_membership_returns_null_org(self):` 테스트 전체 (line 89)
- 관련 주석 (line 78)

- [ ] **Step 5: stale 주석 정리**

- `conftest.py:2` — 기존 `# All org/membership-based tests have been deleted or rewritten.` 삭제 또는 내용 업데이트.
- `tests/conftest.py:65` — `# --- Domain fixtures (no organization) ---` → `# --- Domain fixtures ---`.
- `main/urls.py:13,15` — 주석 `# Root: onboarding router (routes by membership status)` 와 `# Dashboard: explicit path only (protected by membership_required in t04)` 를 각각 `# Root: onboarding router` / `# Dashboard: level_required gated` 로 교체.

- [ ] **Step 6: 모든 변경된 파일의 organization 잔존 확인**

Run: `uv run grep -rn "organization" --include='*.py' projects/services/ candidates/views_extension.py tests/test_extension_api.py conftest.py tests/conftest.py main/urls.py`

Expected: 결과 없음. (단, `candidates/services/detail_normalizers.py` 의 `"organization"` 문자열은 LLM 프롬프트 파싱 용도이므로 남겨도 됨 — 결과에 해당 파일이 나와도 제외 확인).

- [ ] **Step 7: 회귀 테스트**

Run: `uv run pytest -q -x`
Expected: 973 passed (기존 extension 테스트 1개 삭제돼 972 될 수 있음).

- [ ] **Step 8: 커밋**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: drop dead organization params and stale comments

Single-tenant refactor left organization=None dangling in voice, matching,
and extension layers. Removed the parameters, their callers, the extension
API response field, and the related test assertions. Also cleaned up a
handful of stale membership/organization comments.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 전체 회귀 + 린트

**Files:** (no code changes)

- [ ] **Step 1: 풀 테스트**

Run: `uv run pytest -q`
Expected: 972~974 passed, 5 skipped (Task 8에서 1건 제거).

- [ ] **Step 2: 린트**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: 포맷 점검**

Run: `uv run ruff format --check .`
Expected: 변경 없음. 변경 필요하면 `uv run ruff format .` 실행 후 커밋.

- [ ] **Step 4: 최종 검증**

Run:
```bash
uv run grep -cn "get_object_or_404(Project\|get_object_or_404(Application\|get_object_or_404(ActionItem\|get_object_or_404(Interview\|get_object_or_404(Submission" projects/views.py projects/views_voice.py projects/views_telegram.py
```
Expected: 0.

- [ ] **Step 5: 커밋 (수정분 있으면)**

```bash
git status
# 변경 있으면:
git add -A
git commit -m "$(cat <<'EOF'
chore: final ruff format after scope refactor

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 완료 조건 (Plan Exit)

- 전체 테스트 green (+`tests/test_work_scope_404.py`, +`tests/accounts/test_scoped_object.py`)
- `ruff check` 통과
- `projects/views*.py` 내 `get_object_or_404(<업무모델>, ...)` 잔존 0건
- `organization` 키워드가 `projects/services/voice/*`, `projects/services/candidate_matching.py`, `candidates/views_extension.py` 에 잔존 0건
- `close_overdue_projects` 배치 런타임 에러 없이 실행 가능
- Level 1 직원 계정으로 남의 project detail URL 접근 시 실제로 404 반환 (수동 검증: `./dev.sh` 환경에서 staff 계정으로 로그인 후 URL 직입)
