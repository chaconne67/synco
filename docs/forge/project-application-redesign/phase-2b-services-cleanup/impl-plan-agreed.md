# Phase 2b — 기존 서비스 레거시 정리

**전제**: [Phase 2a](phase-2a-services-core.md) 완료. 신규 서비스 3개와 signal이 동작함.
**목표**: 기존 `services/` 파일 7개에서 삭제된 레거시 참조(옛 ProjectStatus 멤버, Contact, Offer, lifecycle import)를 모두 제거하고, 새 서비스가 대체할 부분은 호출부를 재배선. `services/lifecycle.py`의 비즈니스 로직은 적절한 모듈로 이전 후 shim으로 축소.
**예상 시간**: 0.5일
**리스크**: 소 (대부분 기계적 치환)

---

## 1. 목표 상태

- `services/lifecycle.py`에서 비즈니스 로직(`apply_interview_result`, `InvalidTransition`, `INTERVIEW_RESULT_TRANSITIONS`) → `services/action_lifecycle.py`로 이전. 나머지 legacy stub은 shim으로 남기거나, voice/ import 경로 업데이트 후 삭제
- `services/collision.py`, `dashboard.py`, `auto_actions.py`, `submission.py`, `urgency.py`, `approval.py`, `news/matcher.py`에서 **삭제된 레거시 ProjectStatus 멤버**(`NEW`, `SEARCHING`, `RECOMMENDING`, `INTERVIEWING`, `NEGOTIATING`, `PENDING_APPROVAL`, `CLOSED_SUCCESS`, `CLOSED_FAIL`, `CLOSED_CANCEL`) 및 `Contact`·`Offer` 참조가 0건
- `ProjectStatus.OPEN`과 `ProjectStatus.CLOSED`는 정상 사용 — 제거 대상이 아님
- 각 서비스 함수가 새 모델(`phase`, `status`, `Application`, `ActionItem`)로 동작
- `python manage.py check`가 **services 레이어 전체** 통과
- `python manage.py shell`에서 각 서비스 모듈 import 에러 없음

## 2. 사전 조건

- Phase 2a 커밋 완료
- `services/phase.py`, `application_lifecycle.py`, `action_lifecycle.py` 존재
- `signals.py` 재작성 완료

## 3. 영향 범위

### 3.1 이전 대상 (lifecycle.py → action_lifecycle.py)
- `apply_interview_result`, `InvalidTransition`, `INTERVIEW_RESULT_TRANSITIONS`

### 3.2 삭제/축소 파일
- `projects/services/lifecycle.py` → 비즈니스 로직 이전 후 legacy stub shim만 남김 (voice/ 호환)

### 3.3 수정 파일
- `projects/services/collision.py`
- `projects/services/dashboard.py`
- `projects/services/auto_actions.py`
- `projects/services/submission.py`
- `projects/services/urgency.py`
- `projects/services/approval.py`
- `projects/services/news/matcher.py`
- `projects/services/voice/action_executor.py` — lifecycle import 경로를 action_lifecycle으로 업데이트
- 위 파일을 import하는 다른 파일에서 lifecycle import 제거 (주로 `views.py`, Phase 3에서 최종 처리)

### 3.4 참조만 (수정 없음)
- `projects/models.py`
- `projects/signals.py` (Phase 2a에서 이미 완성)

## 4. 태스크 분할

### T2b.1 — 참조 인벤토리
**작업**: 각 파일의 레거시 참조를 목록화.

```bash
grep -n "NEW\|SEARCHING\|RECOMMENDING\|INTERVIEWING\|NEGOTIATING\|PENDING_APPROVAL\|CLOSED_SUCCESS\|CLOSED_FAIL\|CLOSED_CANCEL\|Contact\|Offer\|from .lifecycle\|services.lifecycle" \
  projects/services/*.py projects/services/news/*.py projects/services/voice/*.py | tee /tmp/services_refs.txt
```

**산출물**: 어떤 파일의 몇 번째 줄에 어떤 참조가 있는지 표로 정리.

예시:
```
services/collision.py:12  ProjectStatus.CLOSED_SUCCESS
services/collision.py:13  ProjectStatus.CLOSED_FAIL
services/collision.py:14  ProjectStatus.CLOSED_CANCEL
services/dashboard.py:17  (현재 ProjectStatus.OPEN → 유지)
services/approval.py:50   ProjectStatus.NEW → ProjectStatus.OPEN으로 변경
services/voice/action_executor.py:31  from projects.services.lifecycle import ...
...
```

이 인벤토리가 T2b.2 ~ T2b.11의 체크리스트가 됨.

---

### T2b.2 — `services/lifecycle.py` 로직 이전 + shim 축소
**파일**: `projects/services/lifecycle.py`, `projects/services/action_lifecycle.py`
**작업**:
1. `apply_interview_result`, `InvalidTransition`, `INTERVIEW_RESULT_TRANSITIONS`를 `services/action_lifecycle.py`로 이전 (함수 시그니처 유지)
2. `services/lifecycle.py`를 shim으로 축소:
   ```python
   """Legacy shim — real implementations moved to action_lifecycle.py.
   
   voice/action_executor.py가 이 모듈을 top-level import하므로, 앱 부팅을 위해 유지.
   Phase 6에서 voice/ 전체 재작성 시 삭제 예정.
   """
   # Re-export for backward compatibility
   from projects.services.action_lifecycle import (
       InvalidTransition,
       apply_interview_result,
   )
   
   def maybe_advance_to_interviewing(project) -> bool:
       return False
   
   def maybe_advance_to_negotiating(project) -> bool:
       return False
   
   def maybe_advance_to_closed_success(project) -> bool:
       return False
   
   def is_submission_offer_eligible(submission) -> bool:
       return False
   ```
3. `views.py`에서 lifecycle import가 발견되면 해당 import 라인만 제거. views.py 본문의 전면 재작성은 Phase 3에서 처리하므로, 여기서는 import만 삭제하여 unused import 경고를 줄임.

**검증**:
```bash
# lifecycle shim이 import 가능한지
python -c "from projects.services.lifecycle import apply_interview_result, InvalidTransition; print('OK')"

# voice/action_executor.py가 정상 import되는지
python -c "from projects.services.voice.action_executor import confirm_action; print('OK')"
```

---

### T2b.3 — `services/collision.py` 정리
**파일**: `projects/services/collision.py`
**작업**:
- `CLOSED_STATUSES` 집합을 삭제된 멤버(`CLOSED_SUCCESS/FAIL/CANCEL`)에서 `{ProjectStatus.CLOSED}`로 변경
- 기존 충돌 감지 로직(후보자 중복 등)은 그대로 유지, 상태 참조만 새 필드로 교체

**검증**:
```bash
grep -n "CLOSED_SUCCESS\|CLOSED_FAIL\|CLOSED_CANCEL\|Contact\|Offer" projects/services/collision.py
```
→ 결과 0건.

---

### T2b.4 — `services/dashboard.py` 재작성
**파일**: `projects/services/dashboard.py`
**작업**: 이 파일은 Phase 3 대시보드 뷰가 호출할 서비스 함수들을 제공. 기존 함수를 새 모델 기반으로 교체.

**새 함수들**:

```python
from datetime import timedelta
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Organization, User
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Application,
    Project,
    ProjectPhase,
    ProjectStatus,
)


def get_today_actions(user: User, org: Organization):
    """해당 사용자의 오늘 할 일 (scheduled_at 오늘 또는 due_at 오늘, overdue 제외)."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    return ActionItem.objects.filter(
        assigned_to=user,
        application__project__organization=org,
        status=ActionItemStatus.PENDING,
    ).filter(
        Q(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
        | Q(due_at__gte=max(now, today_start), due_at__lt=today_end)
    ).select_related("application__project", "application__candidate", "action_type")


def get_overdue_actions(user: User, org: Organization):
    """해당 사용자의 마감 지난 액션."""
    now = timezone.now()
    return ActionItem.objects.filter(
        assigned_to=user,
        application__project__organization=org,
        status=ActionItemStatus.PENDING,
        due_at__lt=now,
    ).select_related("application__project", "application__candidate", "action_type")


def get_upcoming_actions(user: User, org: Organization, days=3):
    """해당 사용자의 3일 내 예정 액션 (scheduled_at 또는 due_at 기준)."""
    now = timezone.now()
    soon = now + timedelta(days=days)
    return ActionItem.objects.filter(
        assigned_to=user,
        application__project__organization=org,
        status=ActionItemStatus.PENDING,
    ).filter(
        Q(scheduled_at__gte=now, scheduled_at__lte=soon)
        | Q(due_at__gte=now, due_at__lte=soon)
    ).select_related("application__project", "application__candidate", "action_type").distinct()


def get_project_kanban_cards(org: Organization):
    """2-phase 칸반에 필요한 카드 데이터."""
    now = timezone.now()
    projects = Project.objects.filter(organization=org).annotate(
        active_count=Count(
            "applications",
            filter=Q(
                applications__dropped_at__isnull=True,
                applications__hired_at__isnull=True,
            ),
        ),
    ).select_related("client").prefetch_related("assigned_consultants")

    cards = {
        ProjectPhase.SEARCHING: [],
        ProjectPhase.SCREENING: [],
        "closed": [],
    }

    for project in projects:
        pending_actions = ActionItem.objects.filter(
            application__project=project,
            status=ActionItemStatus.PENDING,
        )
        overdue_count = pending_actions.filter(due_at__lt=now).count()
        pending_count = pending_actions.count()

        card = {
            "project": project,
            "active_count": project.active_count,
            "pending_actions_count": pending_count,
            "overdue_count": overdue_count,
            "deadline": project.deadline,
            "days_until_deadline": (project.deadline - now.date()).days if project.deadline else None,
        }

        if project.status == ProjectStatus.CLOSED:
            cards["closed"].append(card)
        else:
            cards[project.phase].append(card)

    return cards


def get_pending_approvals(org: Organization):
    """미처리 승인 요청 목록 (OWNER 전용). 기존 API 유지."""
    from projects.models import ProjectApproval
    return ProjectApproval.objects.filter(
        project__organization=org,
        status=ProjectApproval.Status.PENDING,
    ).select_related("project", "requested_by")
```

**기존 API 호환 참고**: `get_weekly_schedule`, `get_pipeline_summary`, `get_recent_activities`, `get_team_summary`는 Phase 3에서 views.py가 새 API로 전환될 때 제거. Phase 2b에서는 삭제하되, views.py의 lazy import(함수 내부 import)이므로 import-time 에러는 발생하지 않음.

**검증**: 함수들이 import 가능하고, 빈 DB에서도 empty dict나 empty list를 반환함.

---

### T2b.5 — `services/auto_actions.py` 정리
**파일**: `projects/services/auto_actions.py`
**작업**:
- 삭제된 `ProjectStatus` 멤버 기반 자동 트리거 참조 제거
- **기존 공개 API 보존**: `get_pending_actions`, `apply_action`, `dismiss_action`, `ConflictError`, `ValidationError` — views.py에서 현재 사용 중이므로 함수명·시그니처 유지
- 새 helper 추가 (생성하지 않음 — 제안만):

```python
from projects.models import ActionType, Application


DEFAULT_FIRST_ACTION_CODE = "reach_out"


def suggest_initial_action(application: Application) -> ActionType | None:
    """Application 생성 직후 UI에 제안할 첫 ActionType. 생성은 하지 않음."""
    try:
        return ActionType.objects.get(code=DEFAULT_FIRST_ACTION_CODE, is_active=True)
    except ActionType.DoesNotExist:
        return None
```

- `AutoAction` 모델 자체는 유지. `ACTION_DATA_SCHEMA` 내 `offer_template` 등 레거시 스키마 정리는 Phase 6 범위 (FINAL-SPEC: AutoAction은 변경 없는 테이블)

**검증**: 기존 `get_pending_actions`, `apply_action` 함수가 import 가능하고 정상 동작.

---

### T2b.6 — `services/submission.py` 재작성
**파일**: `projects/services/submission.py`
**작업**:
- 기존 `Submission.Status` 전이 로직 제거 (status 필드 자체가 Phase 1에서 제거됨 — 현재 코드는 import 시점에 이미 broken)
- 새 함수:
  ```python
  from projects.models import ActionItem, Submission


  def get_or_create_for_action(action_item: ActionItem, *, consultant=None) -> Submission:
      """submit_to_client ActionItem에 Submission을 1:1로 붙임."""
      if action_item.action_type.code != "submit_to_client":
          raise ValueError("submission only for submit_to_client action")
      submission, _ = Submission.objects.get_or_create(
          action_item=action_item,
          defaults={"consultant": consultant},
      )
      return submission
  ```
- 기존 `AI 초안 생성` 관련 헬퍼는 보존 (SubmissionDraft 파이프라인 호환). draft_generator, draft_converter, draft_finalizer, draft_pipeline, draft_consultation은 별도 파일이므로 영향 없음.

**검증**: import 에러 없음.

---

### T2b.7 — `services/urgency.py` 확인
**파일**: `projects/services/urgency.py`
**작업**:
- 삭제된 `ProjectStatus` 멤버 참조가 있으면 `phase` / `status` 새 필드로 교체
- `days_elapsed` 기반 긴급도는 유지 가능
- 선택: ActionItem `due_at` 기반 새 긴급도 함수 추가 (Phase 4에서 사용될 수 있음)

---

### T2b.8 — `services/approval.py` 수정
**파일**: `projects/services/approval.py`
**작업**:
- `approve_project()`: `project.status = ProjectStatus.NEW` → `project.status = ProjectStatus.OPEN`으로 변경
- `_safe_delete_pending_project()`: `project.contacts.exists() or project.submissions.exists()` → `project.applications.exists()`로 변경. 새 모델에서 Application이 실질 하위 데이터이므로, Application이 존재하면 삭제 차단
- `ProjectApproval` 모델 기반 로직은 유지
- 기존 충돌 감지 + 승인 플로우는 그대로

**검증**:
```bash
grep -n "ProjectStatus.NEW\|contacts\.exists\|submissions\.exists" projects/services/approval.py
```
→ 결과 0건.

---

### T2b.9 — `services/news/matcher.py` 수정
**파일**: `projects/services/news/matcher.py`
**작업**:
- 삭제된 `ProjectStatus` 멤버(`NEW`, `SEARCHING`, `RECOMMENDING`, `INTERVIEWING`, `NEGOTIATING`) 참조 제거
- "활성 프로젝트" 필터 → `.filter(status=ProjectStatus.OPEN)` 사용

---

### T2b.10 — import 정리
**작업**: 각 수정 파일의 import 섹션에서 사용하지 않게 된 import 삭제.

```bash
uv run ruff check projects/services/ --fix
```

**예상**: ruff가 사용하지 않는 import를 자동 제거.

---

### T2b.11 — 최종 grep 스캔
**작업**:
```bash
# 삭제된 레거시 ProjectStatus 멤버 참조 (ProjectStatus.OPEN/CLOSED는 정상)
grep -rn "NEW\|SEARCHING\|RECOMMENDING\|INTERVIEWING\|NEGOTIATING\|PENDING_APPROVAL\|CLOSED_SUCCESS\|CLOSED_FAIL\|CLOSED_CANCEL" projects/services/*.py projects/services/news/*.py | grep -i "ProjectStatus\|Status\." 

# Contact 참조
grep -rn "from projects.models import.*Contact\|models\.Contact\b" projects/services/

# Offer 참조
grep -rn "from projects.models import.*Offer\|models\.Offer\b" projects/services/

# lifecycle 직접 비즈니스 로직 호출 (shim re-export는 허용)
grep -rn "from .lifecycle import.*apply_interview\|from projects.services.lifecycle import.*apply_interview" projects/
```

**예상**: 모두 0건 (lifecycle shim의 re-export import는 제외). 남아있으면 해당 파일에 복귀하여 추가 정리.

---

### T2b.12 — services 레이어 Django check
**작업**:
```bash
uv run python manage.py check
```

**예상**: services 레이어 에러 0건. 
- 단 `views.py`, `forms.py`에서 삭제된 `ProjectStatus` 멤버·`Contact`·`Offer` 참조로 인한 에러는 **여전히 남아있을 수 있음** (Phase 3에서 정리)
- services 파일들 간 상호 import가 정상 해결되는지 확인

추가 확인:
```bash
uv run python manage.py shell -c "
from projects.services import phase, application_lifecycle, action_lifecycle
from projects.services import collision, dashboard, auto_actions, submission, urgency, approval
from projects.services.lifecycle import apply_interview_result, InvalidTransition
print('all service modules imported successfully')
"
```

---

### T2b.13 — 기본 스모크 테스트
**작업**: Phase 2a에서 작성한 테스트가 여전히 통과하는지 확인.

```bash
uv run pytest projects/tests/ -v
```

**예상**: 기존 테스트 통과 유지.

---

## 5. 검증 체크리스트

- [ ] `services/lifecycle.py` 비즈니스 로직 → `action_lifecycle.py`로 이전됨
- [ ] `services/lifecycle.py` shim으로 축소됨 (re-export + legacy stub만)
- [ ] `services/voice/action_executor.py` lifecycle import → action_lifecycle 경로로 업데이트 또는 shim 경유
- [ ] `services/collision.py` 정리 완료 (CLOSED_SUCCESS/FAIL/CANCEL → CLOSED)
- [ ] `services/dashboard.py` 새 함수로 재작성 (org 파라미터 포함, overdue 제외, scheduled_at 포함)
- [ ] `services/auto_actions.py` 레거시 ProjectStatus 참조 제거 + 기존 공개 API 보존
- [ ] `services/submission.py` 새 구조 반영 (기존 broken 코드 제거)
- [ ] `services/urgency.py` 필드 참조 교체
- [ ] `services/approval.py` NEW→OPEN, contacts→applications 변경
- [ ] `services/news/matcher.py` 레거시 ProjectStatus 멤버 제거
- [ ] `grep "NEW\|SEARCHING\|RECOMMENDING\|..." projects/services/` → 0건 (ProjectStatus.OPEN/CLOSED 제외)
- [ ] `grep Contact projects/services/` (직접 model 참조) → 0건
- [ ] `grep Offer projects/services/` (직접 model 참조) → 0건
- [ ] `ruff check projects/services/` 통과
- [ ] `python manage.py check` services 레이어 통과
- [ ] 기존 테스트 통과 유지

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `dashboard.py` 재작성 중 기존 Phase 3 뷰가 이 모듈을 import 중이어서 signature 불일치 | Phase 3에서 views.py를 재작성할 때 dashboard.py signature에 맞춤. 여기서는 signature를 **완성된 형태로 결정**. views.py lazy import이므로 import-time 에러 없음 |
| `auto_actions.py` 기존 API 소비자 파괴 | 기존 공개 API (get_pending_actions 등) 보존. suggest_initial_action만 추가 |
| `lifecycle.py` 삭제 시 voice/ ImportError | 즉시 삭제하지 않음. 비즈니스 로직은 action_lifecycle로 이전, shim으로 남김. voice/ import 경로 업데이트 |
| `collision.py`의 승인 로직이 views.py에서 직접 호출 중 | import 끊어지지 않도록 기존 함수 이름·signature 유지. 내부 구현만 새 모델로 교체 |
| `urgency.py`가 candidates 앱에서도 호출 | 외부 호출부 영향 없도록 반환 타입 유지 |
| `news/matcher.py`의 정규표현식 / 텍스트 매칭 로직이 복잡 | 상태 필드만 교체, 로직 본문은 건드리지 않음 |
| `approval.py` signal과의 충돌 | Phase 2a signal은 Application save 시 phase 재계산. approval의 Project.status = OPEN 설정과 충돌 없음 |
| `submission.py` 기존 코드 broken | Submission.Status 삭제로 이미 broken. 새 함수로 완전 교체 |

## 7. 커밋 포인트

```
chore(projects): clean up legacy refs in services, move lifecycle logic

- Move apply_interview_result to action_lifecycle.py, keep lifecycle.py as shim
- Rewrite services/dashboard.py with ActionItem-based aggregations (org-scoped)
- Add suggest_initial_action to auto_actions.py, preserve existing public API
- Rewrite services/submission.py for ActionItem 1:1 relationship
- Fix approval.py: ProjectStatus.NEW→OPEN, contacts→applications
- Remove legacy ProjectStatus members from collision/urgency/news/matcher
- Update voice/action_executor.py lifecycle import path
- ruff clean, manage.py check passing at services layer

Refs: FINAL-SPEC.md §2, §3
```

## 8. Phase 3a로 넘기는 인터페이스

- 모든 서비스 함수가 새 모델 기반으로 동작
- `get_today_actions(user, org)`, `get_overdue_actions(user, org)`, `get_upcoming_actions(user, org)`, `get_project_kanban_cards(org)` signature 확정
- `application_lifecycle.drop/restore/hire` signature 확정
- `action_lifecycle.create_action/complete_action/skip_action/reschedule_action/propose_next` signature 확정
- `action_lifecycle.apply_interview_result` signature 확정 (lifecycle.py에서 이전됨)
- `auto_actions.get_pending_actions/apply_action/dismiss_action` 기존 API 유지
- Phase 3a의 forms·urls·메인 뷰가 이 서비스 함수만 호출하면 됨

---

**이전 Phase**: [phase-2a-services-core.md](phase-2a-services-core.md)
**다음 Phase**: [phase-3a-views-base.md](phase-3a-views-base.md)

<!-- forge:phase-2b-services-cleanup:impl-plan:complete:2026-04-14T18:15:00Z -->
