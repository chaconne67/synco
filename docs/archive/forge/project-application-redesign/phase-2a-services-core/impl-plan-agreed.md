# Phase 2a — 신규 서비스 3개 + signals 재작성 (확정본)

**전제**: [Phase 1](phase-1-models.md) 완료. 새 모델이 모두 ORM 레벨에서 유효함.
**목표**: 핵심 비즈니스 로직인 phase 파생·Application 생명주기·ActionItem 생명주기 서비스 함수를 만들고, 이 함수들을 자동으로 호출하는 signal을 재작성.
**예상 시간**: 0.5일
**리스크**: 중 (signal 재귀·의존성 설계 중요)
**범위**: 신규 로직만. 기존 서비스(`collision.py`, `dashboard.py` 등)의 `ProjectStatus`·`Contact`·`Offer` 참조 정리는 [Phase 2b](phase-2b-services-cleanup.md)에서 처리.

**담금질 결과**: Codex 전문가 패널(Django Signal/ORM, 도메인 로직, 테스트/회귀) 2라운드. 13개 이슈 중 12개 수용, 1개 Round 2에서 추가 수용. 주요 변경:
- HIRED 처리를 signal → hire() 서비스로 이관 (I-01, I-04)
- select_for_update() + partial UniqueConstraint (I-02)
- sync_project_status_field에서 result 동시 초기화 (I-03)
- 모든 lifecycle 함수에 transaction.atomic() + 전이 가드 (I-05, I-07, I-08)
- losers 드롭을 bulk .update() + 명시적 phase 재계산 (I-06)
- 테스트 위치 확정 + 풀 스위트 게이트 + 자동화 테스트 확장 (I-09~I-13)

---

## 1. 목표 상태

- `projects/services/phase.py` 신규, `compute_project_phase(project)` 구현
- `projects/services/application_lifecycle.py` 신규, `drop / restore / hire` 구현 (**hire()가 HIRED 전체 로직 소유**)
- `projects/services/action_lifecycle.py` 신규, `create_action / complete_action / skip_action / cancel_action / reschedule_action / propose_next` 구현
- `projects/signals.py` 재작성: Application·ActionItem 변경 시 phase 재계산, Project.status/result 자동 동기화 (**HIRED 처리 제외 — hire() 서비스가 담당**)
- `Application` 모델에 partial UniqueConstraint 추가 (동시 hire 방지)
- 테스트: phase 파생 5개 + signal 통합 4개 + 서비스 lifecycle 5개 + seed integrity 1개 = **최소 15개**
- Phase 2a 종료 시점에 `uv run pytest -v`가 그린 (레거시 깨짐은 xfail 처리)
- `python manage.py check`가 새 서비스·signal 관점에서 통과

## 2. 사전 조건

- Phase 1 커밋 완료
- `Project`, `Application`, `ActionItem`, `ActionType`, enum들이 전부 import 가능
- ActionType seed 23개 존재 (특히 `submit_to_client`, `pre_meeting`, `interview_round`, `confirm_hire` 4개 보호 타입 확인)

## 3. 영향 범위

### 3.1 신규 파일
- `projects/services/phase.py`
- `projects/services/application_lifecycle.py`
- `projects/services/action_lifecycle.py`
- `tests/test_phase2a_services.py` (phase 파생 + service lifecycle + signal 통합 + seed integrity)

### 3.2 수정 파일
- `projects/signals.py` (전면 재작성)
- `projects/models.py` (Application에 partial UniqueConstraint 추가)
- `tests/conftest.py` (공용 fixture 추가)

### 3.3 Phase 2b로 이월
- 기존 `services/lifecycle.py`의 함수가 다른 파일에서 import되고 있어도 이 Phase에서는 **그대로 둠**. Phase 2b에서 삭제와 동시에 호출부 정리.

## 4. 태스크 분할

### T2a.1 — `services/phase.py` 신규
**파일**: `projects/services/phase.py`
**작업**:
```python
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Project,
    ProjectPhase,
)

SUBMIT_TO_CLIENT_CODE = "submit_to_client"


def compute_project_phase(project: Project) -> str:
    """OR 규칙: submit_to_client 완료된 활성 ActionItem이 있으면 screening."""
    if project.closed_at is not None:
        return project.phase  # 종료된 프로젝트는 마지막 값 유지

    has_submitted_active = ActionItem.objects.filter(
        application__project=project,
        application__dropped_at__isnull=True,
        application__hired_at__isnull=True,
        action_type__code=SUBMIT_TO_CLIENT_CODE,
        status=ActionItemStatus.DONE,
    ).exists()

    return ProjectPhase.SCREENING if has_submitted_active else ProjectPhase.SEARCHING
```

**검증**: 빈 프로젝트 → `searching`. ActionItem pending → `searching`. ActionItem done → `screening`.

---

### T2a.2 — `services/application_lifecycle.py` 신규
**파일**: `projects/services/application_lifecycle.py`
**작업**:

```python
from django.db import transaction
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    Application,
    DropReason,
    Project,
    ProjectResult,
    ProjectStatus,
)
from projects.services.phase import compute_project_phase


def drop(application: Application, reason: str, actor, note: str = "") -> Application:
    """Application을 드롭 상태로. 기존 pending 액션은 자동 취소."""
    # 전이 가드 [I-07]
    if application.dropped_at is not None:
        raise ValueError("already dropped")
    if application.hired_at is not None:
        raise ValueError("cannot drop a hired application")
    if reason not in DropReason.values:
        raise ValueError(f"invalid drop_reason: {reason}")

    # 원자적 처리 [I-05]
    with transaction.atomic():
        application.dropped_at = timezone.now()
        application.drop_reason = reason
        application.drop_note = note
        application.save(update_fields=["dropped_at", "drop_reason", "drop_note", "updated_at"])
        ActionItem.objects.filter(
            application=application,
            status=ActionItemStatus.PENDING,
        ).update(status=ActionItemStatus.CANCELLED)
    return application


def restore(application: Application, actor) -> Application:
    """드롭 취소. hired 상태나 closed project에서는 복구 불가."""
    # 전이 가드 [I-07]
    if application.dropped_at is None:
        raise ValueError("application is not dropped")
    if application.hired_at is not None:
        raise ValueError("cannot restore a hired application")
    if application.project.closed_at is not None:
        raise ValueError("cannot restore application in a closed project")

    application.dropped_at = None
    application.drop_reason = ""
    application.drop_note = ""
    application.save(update_fields=["dropped_at", "drop_reason", "drop_note", "updated_at"])
    return application


def hire(application: Application, actor) -> Application:
    """입사 확정. 서비스가 프로젝트 자동 종료 + 나머지 Application 드롭을 직접 소유. [I-01, I-02]"""
    # 전이 가드 [I-07]
    if application.dropped_at is not None:
        raise ValueError("cannot hire a dropped application")
    if application.hired_at is not None:
        raise ValueError("already hired")

    with transaction.atomic():
        # 프로젝트 + 활성 Application 락 [I-02]
        project = Project.objects.select_for_update().get(pk=application.project_id)

        if project.closed_at is not None:
            raise ValueError("cannot hire in a closed project")

        # 이미 hired된 Application이 있는지 재검사 (race condition 방지) [I-02]
        existing_hired = Application.objects.select_for_update().filter(
            project=project,
            hired_at__isnull=False,
        ).exists()
        if existing_hired:
            raise ValueError("another application is already hired in this project")

        now = timezone.now()

        # 1. 입사 확정
        application.hired_at = now
        application.save(update_fields=["hired_at", "updated_at"])

        # 2. 프로젝트 자동 종료
        auto_note = f"[자동] {application.candidate} 입사 확정으로 종료"
        project.closed_at = now
        project.status = ProjectStatus.CLOSED
        project.result = ProjectResult.SUCCESS
        project.note = (project.note + "\n" + auto_note).strip() if project.note else auto_note
        project.save(update_fields=[
            "closed_at", "status", "result", "note", "updated_at"
        ])

        # 3. 나머지 활성 Application 전원 드롭 — bulk update [I-01, I-06]
        others = Application.objects.filter(
            project=project,
            dropped_at__isnull=True,
            hired_at__isnull=True,
        ).exclude(id=application.id)

        drop_note = f"입사자({application.candidate}) 확정으로 포지션 마감"
        others.update(
            dropped_at=now,
            drop_reason=DropReason.OTHER,
            drop_note=drop_note,
            updated_at=now,
        )

        # 4. losers의 pending ActionItem 전원 취소 [I-01]
        ActionItem.objects.filter(
            application__project=project,
            application__dropped_at=now,  # 방금 드롭한 Application들
            status=ActionItemStatus.PENDING,
        ).update(status=ActionItemStatus.CANCELLED)

        # 5. 명시적 phase 재계산 1회 [I-06]
        new_phase = compute_project_phase(project)
        if project.phase != new_phase:
            Project.objects.filter(pk=project.pk).update(phase=new_phase)

    return application
```

**검증**:
- `drop` 호출 시 pending ActionItem이 cancelled로 바뀜 (atomic)
- `restore` 호출 시 dropped_at=None. closed project에서 ValueError
- `hire` 호출 시: hired_at 세팅 + project 종료 + 나머지 드롭 + pending 취소 (단일 트랜잭션)
- 동시 hire 시 두 번째 요청이 ValueError 발생
- 이중 drop/hire 시 ValueError

---

### T2a.2b — Application 모델에 partial UniqueConstraint 추가 [I-02]
**파일**: `projects/models.py`
**작업**: Application.Meta.constraints에 추가:

```python
models.UniqueConstraint(
    fields=["project"],
    condition=models.Q(hired_at__isnull=False),
    name="unique_hired_per_project",
),
```

**마이그레이션**: `uv run python manage.py makemigrations projects`

---

### T2a.3 — `services/action_lifecycle.py` 신규
**파일**: `projects/services/action_lifecycle.py`
**작업**:
```python
from datetime import datetime

from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
)


def create_action(
    application: Application,
    action_type: ActionType,
    actor,
    *,
    title: str = "",
    channel: str = "",
    scheduled_at: datetime | None = None,
    due_at: datetime | None = None,
    parent_action: ActionItem | None = None,
    note: str = "",
) -> ActionItem:
    # 가드: 비활성 타입 금지
    if not action_type.is_active:
        raise ValueError(f"inactive action_type: {action_type.code}")
    # 가드: 종결된 Application/Project에 새 액션 생성 금지 [I-08]
    if not application.is_active:
        raise ValueError("cannot create action on inactive application")
    if application.project.closed_at is not None:
        raise ValueError("cannot create action on closed project")

    if not title:
        title = f"{application.candidate} · {action_type.label_ko}"
    return ActionItem.objects.create(
        application=application,
        action_type=action_type,
        title=title,
        channel=channel or action_type.default_channel,
        scheduled_at=scheduled_at,
        due_at=due_at,
        parent_action=parent_action,
        note=note,
        assigned_to=actor,
        created_by=actor,
        status=ActionItemStatus.PENDING,
    )


def _require_pending(action: ActionItem) -> None:
    """상태 전이 전 pending 상태 검증 [I-08]"""
    if action.status != ActionItemStatus.PENDING:
        raise ValueError(f"action is {action.status}, expected pending")


def complete_action(
    action: ActionItem,
    actor,
    *,
    result: str = "",
    note: str = "",
) -> ActionItem:
    _require_pending(action)
    action.status = ActionItemStatus.DONE
    action.completed_at = timezone.now()
    if result:
        action.result = result
    if note:
        action.note = note
    action.save(update_fields=["status", "completed_at", "result", "note", "updated_at"])
    return action


def skip_action(action: ActionItem, actor, *, note: str = "") -> ActionItem:
    _require_pending(action)
    action.status = ActionItemStatus.SKIPPED
    action.completed_at = timezone.now()
    if note:
        action.note = note
    action.save(update_fields=["status", "completed_at", "note", "updated_at"])
    return action


def cancel_action(action: ActionItem, actor) -> ActionItem:
    _require_pending(action)
    action.status = ActionItemStatus.CANCELLED
    action.save(update_fields=["status", "updated_at"])
    return action


def reschedule_action(
    action: ActionItem,
    actor,
    *,
    new_due_at: datetime | None = None,
    new_scheduled_at: datetime | None = None,
) -> ActionItem:
    _require_pending(action)
    fields = ["updated_at"]
    if new_due_at is not None:
        action.due_at = new_due_at
        fields.append("due_at")
    if new_scheduled_at is not None:
        action.scheduled_at = new_scheduled_at
        fields.append("scheduled_at")
    action.save(update_fields=fields)
    return action


def propose_next(action: ActionItem) -> list[ActionType]:
    """완료된 액션의 action_type.suggests_next 기반 다음 액션 후보."""
    if action.status != ActionItemStatus.DONE:
        return []
    codes = action.action_type.suggests_next or []
    return list(
        ActionType.objects.filter(code__in=codes, is_active=True).order_by("sort_order")
    )
```

**검증**:
- `create_action`이 비활성 Application/종료된 Project에서 ValueError
- `complete_action` 후 `propose_next`가 suggests_next 코드를 정확히 반환
- `skip/cancel/reschedule`이 non-pending 액션에서 ValueError
- `reschedule_action`이 부분 업데이트 (일부 인자만 전달 시)

---

### T2a.4 — `signals.py` 재작성
**파일**: `projects/signals.py`
**작업**: 기존 로직 전부 제거 후 아래 내용으로 교체.

**핵심 변경 대비 원본:**
- `on_application_hired` **제거** — hire() 서비스가 직접 처리 [I-01, I-04]
- `sync_project_status_field` — `result` 동시 초기화 추가 [I-03]

```python
import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from projects.models import (
    ActionItem,
    Application,
    Project,
    ProjectStatus,
)
from projects.services.phase import compute_project_phase

logger = logging.getLogger(__name__)


def _sync_phase(project: Project) -> None:
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        Project.objects.filter(pk=project.pk).update(phase=new_phase)


@receiver([post_save, post_delete], sender=ActionItem)
def recompute_phase_on_action_change(sender, instance, **kwargs):
    try:
        project = instance.application.project
    except Application.DoesNotExist:
        return
    _sync_phase(project)


@receiver([post_save, post_delete], sender=Application)
def recompute_phase_on_application_change(sender, instance, **kwargs):
    _sync_phase(instance.project)


@receiver(post_save, sender=Project)
def sync_project_status_field(sender, instance: Project, **kwargs):
    """closed_at과 status/result 필드를 항상 동기화. signal 재귀 방지 위해 .update() 사용."""
    expected_status = ProjectStatus.CLOSED if instance.closed_at else ProjectStatus.OPEN

    # [I-03] reopen 시 result도 초기화 — DB CheckConstraint 위반 방지
    updates = {}
    if instance.status != expected_status:
        updates["status"] = expected_status
    if expected_status == ProjectStatus.OPEN and instance.result:
        updates["result"] = ""
    if updates:
        Project.objects.filter(pk=instance.pk).update(**updates)
```

**signal 재귀 방지 체크리스트**:
- `_sync_phase`: `Project.save` 대신 `Project.objects.filter().update()` 사용 → post_save 재트리거 없음
- `sync_project_status_field`: 동일하게 `.update()` 사용
- `on_application_hired` **삭제됨** — hire() 서비스에서 `.save(update_fields=...)` 호출하므로 post_save는 발생하지만, `sync_project_status_field`가 `.update()`로만 처리하므로 재귀 없음

**신규 receiver 등록**: `projects/apps.py`의 `ProjectsConfig.ready()`에서 `import projects.signals`가 이미 있는지 확인. 없으면 추가.

---

### T2a.5 — 테스트
**파일**: `tests/test_phase2a_services.py` [I-09: 기존 tests/ 구조에 배치]
**Fixture**: `tests/conftest.py`에 `project`, `application`, `consultant`, `organization`, `client_company`, `candidate` 공용 픽스쳐 추가. [I-09]

**작업**: 4개 카테고리, 최소 15개 테스트.

#### 카테고리 A: Phase 파생 (5개)
```python
import pytest
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    ProjectPhase,
)
from projects.services.phase import compute_project_phase


pytestmark = pytest.mark.django_db


def test_empty_project_is_searching(project):
    assert compute_project_phase(project) == ProjectPhase.SEARCHING


def test_application_without_actions_is_searching(project, application):
    assert compute_project_phase(project) == ProjectPhase.SEARCHING


def test_reach_out_pending_is_searching(application):
    reach_out = ActionType.objects.get(code="reach_out")
    ActionItem.objects.create(
        application=application,
        action_type=reach_out,
        title="연락",
        status=ActionItemStatus.PENDING,
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SEARCHING


def test_submit_to_client_done_is_screening(application):
    submit = ActionType.objects.get(code="submit_to_client")
    ActionItem.objects.create(
        application=application,
        action_type=submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SCREENING


def test_closed_project_keeps_phase(project):
    project.closed_at = timezone.now()
    project.status = "closed"
    project.phase = ProjectPhase.SCREENING
    project.save()
    assert compute_project_phase(project) == ProjectPhase.SCREENING
```

#### 카테고리 B: Signal 통합 (4개) [I-11]
```python
def test_action_done_triggers_screening(application):
    """ActionItem DONE → signal이 project.phase를 screening으로 변경."""
    submit = ActionType.objects.get(code="submit_to_client")
    ActionItem.objects.create(
        application=application,
        action_type=submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert application.project.phase == ProjectPhase.SCREENING


def test_submitted_app_drop_reverts_to_searching(application):
    """submitted app 드롭 → searching 복귀."""
    from projects.services.application_lifecycle import drop
    submit = ActionType.objects.get(code="submit_to_client")
    ActionItem.objects.create(
        application=application,
        action_type=submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    drop(application, "unfit", None)
    application.project.refresh_from_db()
    assert application.project.phase == ProjectPhase.SEARCHING


def test_hire_closes_project_and_drops_others(application, second_application):
    """hire → project closed + 나머지 Application dropped + pending actions cancelled."""
    from projects.services.application_lifecycle import hire
    ActionItem.objects.create(
        application=second_application,
        action_type=ActionType.objects.get(code="reach_out"),
        title="연락",
        status=ActionItemStatus.PENDING,
    )
    hire(application, None)
    application.project.refresh_from_db()
    second_application.refresh_from_db()
    assert application.project.status == "closed"
    assert application.project.result == "success"
    assert second_application.dropped_at is not None
    pending_count = ActionItem.objects.filter(
        application=second_application,
        status=ActionItemStatus.PENDING,
    ).count()
    assert pending_count == 0


def test_reopen_project_clears_result(project):
    """closed → reopen 시 status=open, result='' 자동 동기화."""
    project.closed_at = timezone.now()
    project.status = "closed"
    project.result = "success"
    project.save()
    # reopen
    project.closed_at = None
    project.save()
    project.refresh_from_db()
    assert project.status == "open"
    assert project.result == ""
```

#### 카테고리 C: 서비스 Lifecycle (5개) [I-12]
```python
def test_drop_cancels_pending_actions(application):
    from projects.services.application_lifecycle import drop
    from projects.services.action_lifecycle import create_action
    action = create_action(application, ActionType.objects.get(code="reach_out"), None)
    drop(application, "unfit", None)
    action.refresh_from_db()
    assert action.status == ActionItemStatus.CANCELLED


def test_double_drop_raises(application):
    from projects.services.application_lifecycle import drop
    drop(application, "unfit", None)
    with pytest.raises(ValueError, match="already dropped"):
        drop(application, "unfit", None)


def test_restore_blocked_on_closed_project(application):
    from projects.services.application_lifecycle import drop, restore, hire
    # hire another → project closes
    # ... (fixture: second_application)
    # Then try restore on dropped application → ValueError
    pass  # 구현 시 fixture 활용하여 작성


def test_hire_dropped_raises(application):
    from projects.services.application_lifecycle import drop, hire
    drop(application, "unfit", None)
    with pytest.raises(ValueError, match="cannot hire a dropped"):
        hire(application, None)


def test_create_action_on_dropped_raises(application):
    from projects.services.application_lifecycle import drop
    from projects.services.action_lifecycle import create_action
    drop(application, "unfit", None)
    with pytest.raises(ValueError, match="inactive application"):
        create_action(application, ActionType.objects.get(code="reach_out"), None)
```

#### 카테고리 D: Seed Integrity (1개) [I-13]
```python
def test_action_type_seed_integrity():
    """ActionType seed 23개 + 보호 타입 4개가 존재하고 활성 상태인지 검증."""
    assert ActionType.objects.count() >= 23
    protected_codes = ["submit_to_client", "pre_meeting", "interview_round", "confirm_hire"]
    for code in protected_codes:
        at = ActionType.objects.get(code=code)
        assert at.is_active, f"{code} should be active"
        assert at.is_protected, f"{code} should be protected"
```

**Fixture 추가 (tests/conftest.py)**:
```python
@pytest.fixture
def organization(db):
    from accounts.models import Organization
    return Organization.objects.create(name="테스트 조직")

@pytest.fixture
def consultant(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(username="consultant", password="test")

@pytest.fixture
def client_company(db, organization):
    from clients.models import Client
    return Client.objects.create(name="테스트 고객사", organization=organization)

@pytest.fixture
def candidate(db):
    from candidates.models import Candidate
    return Candidate.objects.create(name_ko="김후보")

@pytest.fixture
def project(db, client_company, organization, consultant):
    from projects.models import Project
    return Project.objects.create(
        title="테스트 프로젝트",
        client=client_company,
        organization=organization,
        created_by=consultant,
    )

@pytest.fixture
def application(db, project, candidate, consultant):
    from projects.models import Application
    return Application.objects.create(
        project=project,
        candidate=candidate,
        created_by=consultant,
    )

@pytest.fixture
def second_application(db, project, consultant):
    from candidates.models import Candidate
    candidate2 = Candidate.objects.create(name_ko="이후보")
    from projects.models import Application
    return Application.objects.create(
        project=project,
        candidate=candidate2,
        created_by=consultant,
    )
```

**주의**: fixture 모델 필드는 구현 시 실제 모델과 대조하여 조정. 위 코드는 최소 필수 필드 예시.

**실행**:
```bash
uv run pytest tests/test_phase2a_services.py -v
```

**예상**: 15개 통과.

---

### T2a.6 — 레거시 테스트 xfail 처리 [I-10]
**작업**: Phase 1 모델 변경(ProjectStatus enum 축소 등)으로 깨지는 기존 테스트를 파악하고 xfail 마킹.

```bash
# 깨지는 테스트 파악
uv run pytest -v 2>&1 | grep FAILED
```

깨지는 테스트마다:
1. 파괴 원인이 Phase 1 모델 변경인지 확인
2. Phase 2a 신규 코드가 원인이 아닌 경우 → `@pytest.mark.xfail(reason="Phase 2b: legacy ProjectStatus cleanup")`
3. Phase 2a 신규 코드가 원인인 경우 → Phase 2a 내에서 수정

**통과 기준**: `uv run pytest -v`에서 FAIL 0개 (xfail은 OK).

---

### T2a.7 — `python manage.py check` 통과
**작업**:
```bash
uv run python manage.py check
```

**예상**:
- 새 `services/phase.py`, `application_lifecycle.py`, `action_lifecycle.py` import 에러 없음
- `signals.py` import 에러 없음
- partial UniqueConstraint migration 적용 완료
- 기존 `services/collision.py`, `dashboard.py` 등의 레거시 참조로 인한 에러는 **여전히 남아있을 수 있음** (Phase 2b에서 정리)

만약 `signals.py` import 시점에 에러가 나면 Phase 2a 내에서 수정. 그 외는 Phase 2b로 넘김.

---

## 5. 검증 체크리스트

- [ ] `services/phase.py` 작성 + import 통과
- [ ] `services/application_lifecycle.py` 작성 + import 통과 (**hire()가 HIRED 전체 로직 포함**)
- [ ] `services/action_lifecycle.py` 작성 + import 통과 (**전이 가드 포함**)
- [ ] `signals.py` 재작성 + receiver 등록 확인 (**on_application_hired 제거, result 동기화 포함**)
- [ ] Application 모델에 partial UniqueConstraint 추가 + migration 생성
- [ ] `tests/test_phase2a_services.py` 최소 15개 테스트 통과
- [ ] 레거시 깨짐 테스트 xfail 처리
- [ ] `uv run pytest -v`에서 FAIL 0개
- [ ] `python manage.py check`가 새 파일 관점에서 통과

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| signal 무한 재귀 | `Project.objects.filter().update()` 사용으로 post_save 우회. 모든 재귀 경로를 자동 테스트로 검증 |
| 동시 hire race condition [I-02] | `select_for_update()` + partial UniqueConstraint 이중 방어 |
| DB CheckConstraint 충돌 [I-03] | `sync_project_status_field`에서 status와 result를 같이 update |
| 기존 `signals.py`에 재설계와 무관한 로직 존재 가능 | Phase 1에서 이미 stripped (현재 signals.py는 빈 placeholder). 별도 이식 불필요 |
| `conftest.py` 픽스쳐 설계 지연 | Phase 2a에서 기본 fixture 작성. 실제 모델과 대조하여 조정 |
| 서비스 함수 naming 충돌 | prefix 없이 `drop` 유지. import 시 `from projects.services import application_lifecycle` 방식으로 네임스페이스 보존 |
| hire() 서비스 복잡도 증가 [I-01] | HIRED 로직을 signal에서 서비스로 모았으므로 단일 트랜잭션에서 테스트·디버깅 가능. 복잡도는 증가하지만 투명성은 향상 |

## 7. 커밋 포인트

```
feat(projects): add phase derivation + Application/ActionItem lifecycle services

- Add services/phase.py with compute_project_phase (OR rule)
- Add services/application_lifecycle.py (drop/restore/hire with full HIRED processing)
- Add services/action_lifecycle.py (create/complete/skip/cancel/reschedule/propose_next)
- Rewrite signals.py: phase recompute + status/result sync (HIRED signal removed)
- Add partial UniqueConstraint for hire race condition prevention
- Add tests/test_phase2a_services.py with 15+ test cases
- xfail legacy tests broken by Phase 1 model changes

Refs: FINAL-SPEC.md §3
Tempered: Codex expert panel (2 rounds, 13 issues)
```

## 8. Phase 2b로 넘기는 인터페이스

- 새 서비스 3개와 signal이 동작함
- **hire() 서비스가 HIRED 전체 로직을 소유** (signal은 phase/status 동기화만)
- 기존 `services/lifecycle.py`는 아직 존재 (Phase 2b에서 삭제)
- 기존 `services/collision.py`, `dashboard.py`, `auto_actions.py`, `submission.py`, `urgency.py`, `approval.py`, `news/matcher.py`의 `ProjectStatus`·`Contact`·`Offer` 참조는 Phase 2b에서 정리
- 레거시 테스트 xfail 해제는 Phase 2b/5에서 처리

---

**이전 Phase**: [phase-1-models.md](phase-1-models.md)
**다음 Phase**: [phase-2b-services-cleanup.md](phase-2b-services-cleanup.md)

<!-- forge:phase-2a-services-core:impl-plan:complete:2026-04-14T17:00:00Z -->
