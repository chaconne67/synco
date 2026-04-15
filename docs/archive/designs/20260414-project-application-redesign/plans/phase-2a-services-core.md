# Phase 2a — 신규 서비스 3개 + signals 재작성

**전제**: [Phase 1](phase-1-models.md) 완료. 새 모델이 모두 ORM 레벨에서 유효함.
**목표**: 핵심 비즈니스 로직인 phase 파생·Application 생명주기·ActionItem 생명주기 서비스 함수를 만들고, 이 함수들을 자동으로 호출하는 signal을 재작성.
**예상 시간**: 0.5일
**리스크**: 중 (signal 재귀·의존성 설계 중요)
**범위**: 신규 로직만. 기존 서비스(`collision.py`, `dashboard.py` 등)의 `ProjectStatus`·`Contact`·`Offer` 참조 정리는 [Phase 2b](phase-2b-services-cleanup.md)에서 처리.

---

## 1. 목표 상태

- `projects/services/phase.py` 신규, `compute_project_phase(project)` 구현
- `projects/services/application_lifecycle.py` 신규, `drop / restore / hire` 구현
- `projects/services/action_lifecycle.py` 신규, `create_action / complete_action / skip_action / cancel_action / reschedule_action / propose_next` 구현
- `projects/signals.py` 재작성: Application·ActionItem 변경 시 phase 재계산, HIRED 자동 종료, Project.status 자동 동기화
- 단위 테스트 `projects/tests/test_phase_derivation.py`(기본 케이스)가 통과
- Phase 2a 종료 시점에 `python manage.py check`가 **새 서비스·signal 관점**에서 통과. 기존 서비스의 레거시 참조는 여전히 남아있을 수 있음(Phase 2b에서 정리)

## 2. 사전 조건

- Phase 1 커밋 완료
- `Project`, `Application`, `ActionItem`, `ActionType`, enum들이 전부 import 가능
- ActionType seed 23개 존재 (특히 `submit_to_client`, `pre_meeting`, `interview_round`, `confirm_hire` 4개 보호 타입 확인)

## 3. 영향 범위

### 3.1 신규 파일
- `projects/services/phase.py`
- `projects/services/application_lifecycle.py`
- `projects/services/action_lifecycle.py`
- `projects/tests/test_phase_derivation.py` (기본 케이스만, 나머지는 Phase 5에서 확장)

### 3.2 수정 파일
- `projects/signals.py` (116줄 → 전면 재작성)

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
from django.utils import timezone
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Application,
    DropReason,
)


def drop(application: Application, reason: str, actor, note: str = "") -> Application:
    """Application을 드롭 상태로. 기존 pending 액션은 자동 취소."""
    if reason not in DropReason.values:
        raise ValueError(f"invalid drop_reason: {reason}")
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
    """드롭 취소. hired 상태는 복구 대상 아님."""
    if application.hired_at is not None:
        raise ValueError("cannot restore a hired application")
    application.dropped_at = None
    application.drop_reason = ""
    application.drop_note = ""
    application.save(update_fields=["dropped_at", "drop_reason", "drop_note", "updated_at"])
    return application


def hire(application: Application, actor) -> Application:
    """입사 확정. signal이 프로젝트 자동 종료 + 나머지 Application 드롭."""
    if application.dropped_at is not None:
        raise ValueError("cannot hire a dropped application")
    application.hired_at = timezone.now()
    application.save(update_fields=["hired_at", "updated_at"])
    return application
```

**검증**: 
- `drop` 호출 시 pending ActionItem이 cancelled로 바뀜
- `restore` 호출 시 dropped_at=None
- `hire` 호출 시 hired_at 세팅 → 이후 signal이 처리

---

### T2a.3 — `services/action_lifecycle.py` 신규
**파일**: `projects/services/action_lifecycle.py`
**작업**:
```python
from datetime import datetime, timedelta

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
    if not action_type.is_active:
        raise ValueError(f"inactive action_type: {action_type.code}")
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


def complete_action(
    action: ActionItem,
    actor,
    *,
    result: str = "",
    note: str = "",
) -> ActionItem:
    action.status = ActionItemStatus.DONE
    action.completed_at = timezone.now()
    if result:
        action.result = result
    if note:
        action.note = note
    action.save(update_fields=["status", "completed_at", "result", "note", "updated_at"])
    return action


def skip_action(action: ActionItem, actor, *, note: str = "") -> ActionItem:
    action.status = ActionItemStatus.SKIPPED
    action.completed_at = timezone.now()
    if note:
        action.note = note
    action.save(update_fields=["status", "completed_at", "note", "updated_at"])
    return action


def cancel_action(action: ActionItem, actor) -> ActionItem:
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
- `create_action`이 모든 필드를 올바르게 초기화
- `complete_action` 후 `propose_next`가 suggests_next 코드를 정확히 반환
- `reschedule_action`이 부분 업데이트 (일부 인자만 전달 시)

---

### T2a.4 — `signals.py` 재작성
**파일**: `projects/signals.py`
**작업**: 기존 로직 전부 제거 후 아래 내용으로 교체.

```python
import logging

from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from projects.models import (
    ActionItem,
    Application,
    DropReason,
    Project,
    ProjectResult,
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


@receiver(post_save, sender=Application)
def on_application_hired(sender, instance: Application, created, **kwargs):
    """HIRED 자동 종료 트리거."""
    if instance.hired_at is None:
        return

    project = instance.project
    if project.closed_at is not None:
        logger.warning(
            "duplicate hire detected: application=%s project=%s already closed",
            instance.id, project.id,
        )
        return

    with transaction.atomic():
        now = timezone.now()

        # 1. 프로젝트 자동 종료
        auto_note = f"[자동] {instance.candidate} 입사 확정으로 종료"
        project.closed_at = now
        project.status = ProjectStatus.CLOSED
        project.result = ProjectResult.SUCCESS
        project.note = (project.note + "\n" + auto_note).strip() if project.note else auto_note
        project.save(update_fields=[
            "closed_at", "status", "result", "note", "updated_at"
        ])

        # 2. 나머지 활성 Application 전원 드롭
        others = Application.objects.filter(
            project=project,
            dropped_at__isnull=True,
            hired_at__isnull=True,
        ).exclude(id=instance.id)

        drop_note = f"입사자({instance.candidate}) 확정으로 포지션 마감"
        for other in others:
            other.dropped_at = now
            other.drop_reason = DropReason.OTHER
            other.drop_note = drop_note
            other.save(update_fields=[
                "dropped_at", "drop_reason", "drop_note", "updated_at"
            ])


@receiver(post_save, sender=Project)
def sync_project_status_field(sender, instance: Project, **kwargs):
    """closed_at과 status 필드를 항상 동기화. signal 재귀 방지 위해 .update() 사용."""
    expected_status = ProjectStatus.CLOSED if instance.closed_at else ProjectStatus.OPEN
    if instance.status != expected_status:
        Project.objects.filter(pk=instance.pk).update(status=expected_status)
```

**signal 재귀 방지 체크리스트**:
- `_sync_phase`: `Project.save` 대신 `Project.objects.filter().update()` 사용 → post_save 재트리거 없음
- `sync_project_status_field`: 동일하게 `.update()` 사용
- `on_application_hired`의 Project.save는 `update_fields`로 명시하되, `sync_project_status_field`가 post_save 안에서 다시 호출되어도 `.update()`이므로 재귀 없음

**신규 receiver 등록**: `projects/apps.py`의 `ProjectsConfig.ready()`에서 `import projects.signals`가 이미 있는지 확인. 없으면 추가.

---

### T2a.5 — `test_phase_derivation.py` 기본 케이스
**파일**: `projects/tests/test_phase_derivation.py`
**작업**: 10개 중 최소 5개 케이스만 Phase 2a에서 작성 (나머지는 Phase 5에서 확장).

```python
import pytest
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
    ProjectPhase,
    ProjectStatus,
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
    project.phase = ProjectPhase.SCREENING
    project.save()
    assert compute_project_phase(project) == ProjectPhase.SCREENING
```

**Fixture**: `conftest.py`에 `project`, `application`, `consultant`, `organization`, `client_company`, `candidate` 공용 픽스쳐 작성.

**실행**:
```bash
uv run pytest projects/tests/test_phase_derivation.py -v
```

**예상**: 5개 통과.

---

### T2a.6 — signal 회귀 수동 확인
**작업**: Django shell에서 빠른 스모크 테스트.

```bash
uv run python manage.py shell
```

```python
from projects.models import Project, Application, ActionItem, ActionType, ActionItemStatus
from projects.services.action_lifecycle import create_action, complete_action
from projects.services.application_lifecycle import drop, hire
from django.contrib.auth import get_user_model

# 픽스쳐 수동 생성 후
p = Project.objects.first()
app = Application.objects.first()
user = get_user_model().objects.first()
submit_type = ActionType.objects.get(code="submit_to_client")

# 제출 액션 생성 → phase 유지 (pending)
action = create_action(app, submit_type, user, title="테스트 제출")
p.refresh_from_db()
print(p.phase)  # searching

# 완료 → phase 전환
complete_action(action, user, result="OK")
p.refresh_from_db()
print(p.phase)  # screening

# 입사 확정 → 자동 종료
hire(app, user)
p.refresh_from_db()
print(p.status, p.closed_at, p.result)  # closed, 시각, success
```

**검증**: 수동으로도 signal이 예상대로 동작.

---

### T2a.7 — `python manage.py check` 부분 통과
**작업**:
```bash
uv run python manage.py check
```

**예상**: 
- 새 `services/phase.py`, `application_lifecycle.py`, `action_lifecycle.py` import 에러 없음
- `signals.py` import 에러 없음
- 기존 `services/collision.py`, `dashboard.py` 등의 레거시 참조로 인한 에러는 **여전히 남아있을 수 있음** (Phase 2b에서 정리)

만약 `signals.py` import 시점에 에러가 나면 Phase 2a 내에서 수정. 그 외는 Phase 2b로 넘김.

---

## 5. 검증 체크리스트

- [ ] `services/phase.py` 작성 + import 통과
- [ ] `services/application_lifecycle.py` 작성 + import 통과
- [ ] `services/action_lifecycle.py` 작성 + import 통과
- [ ] `signals.py` 재작성 + receiver 등록 확인
- [ ] `test_phase_derivation.py` 기본 5개 케이스 통과
- [ ] Django shell 스모크 테스트 (제출 → screening, 입사 → closed)
- [ ] `python manage.py check`가 새 파일 관점에서 통과

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| signal 무한 재귀 | `Project.objects.filter().update()` 사용으로 post_save 우회. 모든 재귀 경로를 수동 테스트로 검증 |
| 기존 `signals.py`에 재설계와 무관한 로직(resume 자동 변환, notification 등)이 섞여있음 | 해당 로직은 새 signals.py에 그대로 이식. 새 receiver와 분리된 섹션에 배치 |
| `conftest.py` 픽스쳐 설계 지연 | Phase 2a에서는 기본 fixture만 (project, application), 나머지는 Phase 5에서 확장 |
| 서비스 함수 naming 충돌 (`drop`은 Python builtin 아님이지만 명확성) | prefix 없이 `drop` 유지. import 시 `from projects.services import application_lifecycle` 방식으로 네임스페이스 보존 |
| `on_application_hired`가 `created=False` 분기를 신경 안 씀 | hired_at 세팅은 update 케이스에서도 발생하므로 created와 무관. signal 조건은 `hired_at is None` 체크로 충분 |

## 7. 커밋 포인트

```
feat(projects): add phase derivation + Application/ActionItem lifecycle services

- Add services/phase.py with compute_project_phase (OR rule)
- Add services/application_lifecycle.py (drop/restore/hire)
- Add services/action_lifecycle.py (create/complete/skip/cancel/reschedule/propose_next)
- Rewrite signals.py: phase recompute + HIRED auto-close + status sync
- Add test_phase_derivation.py with 5 base cases

Refs: FINAL-SPEC.md §3
```

## 8. Phase 2b로 넘기는 인터페이스

- 새 서비스 3개와 signal이 동작함
- 기존 `services/lifecycle.py`는 아직 존재 (Phase 2b에서 삭제)
- 기존 `services/collision.py`, `dashboard.py`, `auto_actions.py`, `submission.py`, `urgency.py`, `approval.py`, `news/matcher.py`의 `ProjectStatus`·`Contact`·`Offer` 참조는 Phase 2b에서 정리

---

**이전 Phase**: [phase-1-models.md](phase-1-models.md)
**다음 Phase**: [phase-2b-services-cleanup.md](phase-2b-services-cleanup.md)
