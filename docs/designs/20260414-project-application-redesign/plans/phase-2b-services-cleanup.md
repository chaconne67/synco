# Phase 2b — 기존 서비스 레거시 정리

**전제**: [Phase 2a](phase-2a-services-core.md) 완료. 신규 서비스 3개와 signal이 동작함.
**목표**: 기존 `services/` 파일 7개에서 `ProjectStatus`·`Contact`·`Offer` 참조를 모두 제거하고, `services/lifecycle.py`를 완전 삭제. 새 서비스가 대체할 부분은 호출부를 재배선.
**예상 시간**: 0.5일
**리스크**: 소 (대부분 기계적 치환)

---

## 1. 목표 상태

- `services/lifecycle.py` 파일 **완전 삭제**, 모든 import 제거
- `services/collision.py`, `dashboard.py`, `auto_actions.py`, `submission.py`, `urgency.py`, `approval.py`, `news/matcher.py`에서 `ProjectStatus`·`Contact`·`Offer` grep 결과 0건
- 각 서비스 함수가 새 모델(`phase`, `status`, `Application`, `ActionItem`)로 동작
- `python manage.py check`가 **services 레이어 전체** 통과
- `python manage.py shell`에서 각 서비스 모듈 import 에러 없음

## 2. 사전 조건

- Phase 2a 커밋 완료
- `services/phase.py`, `application_lifecycle.py`, `action_lifecycle.py` 존재
- `signals.py` 재작성 완료

## 3. 영향 범위

### 3.1 삭제 파일
- `projects/services/lifecycle.py`

### 3.2 수정 파일
- `projects/services/collision.py`
- `projects/services/dashboard.py`
- `projects/services/auto_actions.py`
- `projects/services/submission.py`
- `projects/services/urgency.py`
- `projects/services/approval.py`
- `projects/services/news/matcher.py`
- 위 파일을 import하는 다른 파일에서 lifecycle import 제거 (주로 `views.py`, Phase 3에서 최종 처리)

### 3.3 참조만 (수정 없음)
- `projects/models.py`
- `projects/signals.py` (Phase 2a에서 이미 완성)

## 4. 태스크 분할

### T2b.1 — 참조 인벤토리
**작업**: 각 파일의 레거시 참조를 목록화.

```bash
grep -n "ProjectStatus\|Contact\|Offer\|from .lifecycle\|services.lifecycle" \
  projects/services/*.py projects/services/news/*.py | tee /tmp/services_refs.txt
```

**산출물**: 어떤 파일의 몇 번째 줄에 어떤 참조가 있는지 표로 정리.

예시:
```
services/collision.py:12  from projects.models import ProjectStatus
services/collision.py:45  if project.status == ProjectStatus.PENDING_APPROVAL:
services/dashboard.py:13  ProjectStatus.SEARCHING
services/auto_actions.py:30  ProjectStatus.NEW 기반 트리거
...
```

이 인벤토리가 T2b.2 ~ T2b.8의 체크리스트가 됨.

---

### T2b.2 — `services/lifecycle.py` 삭제
**파일**: `projects/services/lifecycle.py`
**작업**:
1. 이 파일을 import하는 호출부 조사:
   ```bash
   grep -rn "from projects.services.lifecycle\|from .lifecycle" projects/
   ```
2. 각 호출부에서 import 제거. 호출 함수가 Phase 2a 서비스로 대체 가능하면 치환:
   - 기존 `maybe_advance_to_interviewing(project)` → 삭제 (새 모델에서는 불필요. phase는 signal이 파생)
   - 기존 `maybe_advance_to_negotiating(project)` → 삭제
   - 기타 phase 전이 함수 모두 삭제
3. 파일 자체 제거:
   ```bash
   rm projects/services/lifecycle.py
   ```

**검증**:
```bash
grep -rn "services\.lifecycle\|from .lifecycle import" projects/
```
→ 결과 0건.

**주의**: `views.py`에서 lifecycle import가 발견되면 해당 import 라인만 제거. views.py 본문의 전면 재작성은 Phase 3에서 처리하므로, 여기서는 import만 삭제하여 ImportError를 피함.

---

### T2b.3 — `services/collision.py` 정리
**파일**: `projects/services/collision.py`
**작업**:
- `ProjectStatus` import 제거
- `PENDING_APPROVAL` 기반 로직이 있으면 `ProjectApproval` 모델을 참조하도록 재배선 (이 모델은 유지됨)
- 기존 충돌 감지 로직(후보자 중복 등)은 그대로 유지, Project 상태 참조만 새 필드(`phase`, `status`)로 교체
- 필요 시 `.filter(status=ProjectStatus.OPEN)` 같은 새 쿼리 사용

**검증**:
```bash
grep -n "ProjectStatus\|Contact\|Offer" projects/services/collision.py
```
→ 결과 0건.

---

### T2b.4 — `services/dashboard.py` 재작성
**파일**: `projects/services/dashboard.py`
**작업**: 이 파일은 Phase 3 대시보드 뷰가 호출할 서비스 함수들을 제공. 재작성 범위가 크므로 기존 함수를 한 번에 교체.

**새 함수들**:

```python
from datetime import timedelta
from django.db.models import Count, Q
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    Application,
    Project,
    ProjectPhase,
    ProjectStatus,
)


def get_today_actions(user):
    """해당 사용자의 오늘 할 일 (scheduled_at 오늘 또는 due_at 오늘)."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    return ActionItem.objects.filter(
        assigned_to=user,
        status=ActionItemStatus.PENDING,
    ).filter(
        Q(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
        | Q(due_at__gte=today_start, due_at__lt=today_end)
    ).select_related("application__project", "application__candidate", "action_type")


def get_overdue_actions(user):
    """해당 사용자의 마감 지난 액션."""
    now = timezone.now()
    return ActionItem.objects.filter(
        assigned_to=user,
        status=ActionItemStatus.PENDING,
        due_at__lt=now,
    ).select_related("application__project", "application__candidate", "action_type")


def get_upcoming_actions(user, days=3):
    """해당 사용자의 3일 내 예정 액션."""
    now = timezone.now()
    soon = now + timedelta(days=days)
    return ActionItem.objects.filter(
        assigned_to=user,
        status=ActionItemStatus.PENDING,
        due_at__gte=now,
        due_at__lte=soon,
    ).select_related("application__project", "application__candidate", "action_type")


def get_project_kanban_cards(organization):
    """2-phase 칸반에 필요한 카드 데이터."""
    now = timezone.now()
    projects = Project.objects.filter(organization=organization).annotate(
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
```

**검증**: 함수들이 import 가능하고, 빈 DB에서도 empty dict나 empty list를 반환함.

---

### T2b.5 — `services/auto_actions.py` 재작성
**파일**: `projects/services/auto_actions.py`
**작업**:
- 기존 `ProjectStatus.NEW`, `ProjectStatus.SEARCHING` 기반 자동 트리거 전부 제거
- `AutoAction` 모델 자체는 유지 (외부 이벤트 기반 자동 생성물용)
- 새 트리거:
  - Application 생성 직후에 기본 ActionItem(예: `reach_out`) 자동 제안을 반환하는 helper
  - **자동 생성하지 않음** — 컨설턴트가 UI에서 확인 후 생성 (사장님 결정: 자동 체인은 제안, 생성은 수동)

**새 helper 예시**:
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

**검증**: 기존 `AutoAction` 관련 뷰/템플릿은 Phase 3/4에서 처리.

---

### T2b.6 — `services/submission.py` 재작성
**파일**: `projects/services/submission.py`
**작업**:
- 기존 `Submission.status` 전이 로직 제거 (status 필드 자체가 Phase 1에서 제거됨)
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
- 기존 `AI 초안 생성` 관련 헬퍼는 유지 (SubmissionDraft 파이프라인 호환)

**검증**: import 에러 없음.

---

### T2b.7 — `services/urgency.py` 확인
**파일**: `projects/services/urgency.py`
**작업**:
- `ProjectStatus` 참조가 있으면 `phase` / `status` 새 필드로 교체
- `days_elapsed` 기반 긴급도는 유지 가능
- 선택: ActionItem `due_at` 기반 새 긴급도 함수 추가 (Phase 4에서 사용될 수 있음)

---

### T2b.8 — `services/approval.py` 수정
**파일**: `projects/services/approval.py`
**작업**:
- `ProjectStatus.PENDING_APPROVAL` 참조 제거
- `ProjectApproval` 모델 기반 로직은 유지
- 기존 충돌 감지 + 승인 플로우는 그대로

---

### T2b.9 — `services/news/matcher.py` 수정
**파일**: `projects/services/news/matcher.py`
**작업**:
- `ProjectStatus` 참조 제거
- "활성 프로젝트" 필터 → `.filter(status=ProjectStatus.OPEN)` 새 필드 사용

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
# ProjectStatus 참조
grep -rn "ProjectStatus" projects/services/ projects/services/news/

# Contact 참조
grep -rn "from projects.models import.*Contact\|models\.Contact\b" projects/services/

# Offer 참조
grep -rn "from projects.models import.*Offer\|models\.Offer\b" projects/services/

# lifecycle import
grep -rn "services\.lifecycle\|from .lifecycle" projects/
```

**예상**: 모두 0건. 남아있으면 해당 파일에 복귀하여 추가 정리.

---

### T2b.12 — services 레이어 Django check
**작업**:
```bash
uv run python manage.py check
```

**예상**: services 레이어 에러 0건. 
- 단 `views.py`, `forms.py`에서 `ProjectStatus`·`Contact`·`Offer` 참조로 인한 에러는 **여전히 남아있을 수 있음** (Phase 3에서 정리)
- services 파일들 간 상호 import가 정상 해결되는지 확인

추가 확인:
```bash
uv run python manage.py shell -c "
from projects.services import phase, application_lifecycle, action_lifecycle
from projects.services import collision, dashboard, auto_actions, submission, urgency, approval
print('all service modules imported successfully')
"
```

---

### T2b.13 — 기본 스모크 테스트
**작업**: Phase 2a에서 작성한 `test_phase_derivation.py`가 여전히 통과하는지 확인.

```bash
uv run pytest projects/tests/test_phase_derivation.py -v
```

**예상**: 5개 케이스 통과 유지.

---

## 5. 검증 체크리스트

- [ ] `services/lifecycle.py` 삭제됨
- [ ] `services/collision.py` 정리 완료
- [ ] `services/dashboard.py` 새 함수로 재작성
- [ ] `services/auto_actions.py` ProjectStatus 참조 제거
- [ ] `services/submission.py` 새 구조 반영
- [ ] `services/urgency.py` 필드 참조 교체
- [ ] `services/approval.py` ProjectStatus 제거
- [ ] `services/news/matcher.py` ProjectStatus 제거
- [ ] `grep ProjectStatus projects/services/` → 0건
- [ ] `grep Contact projects/services/` (직접 model 참조) → 0건
- [ ] `grep Offer projects/services/` (직접 model 참조) → 0건
- [ ] `grep services.lifecycle projects/` → 0건
- [ ] `ruff check projects/services/` 통과
- [ ] `python manage.py check` services 레이어 통과
- [ ] `test_phase_derivation.py` 통과 유지

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| `dashboard.py` 재작성 중 기존 Phase 3 뷰가 이 모듈을 import 중이어서 signature 불일치 | Phase 3에서 views.py를 재작성할 때 dashboard.py signature에 맞춤. 여기서는 signature를 **완성된 형태로 결정** |
| `AutoAction` 기존 사용처 (ProjectStatus 트리거)가 view/template에 분산 | Phase 3/4에서 정리. Phase 2b에서는 서비스 함수 단위만 |
| `collision.py`의 승인 로직이 views.py에서 직접 호출 중 | import 끊어지지 않도록 기존 함수 이름·signature 유지. 내부 구현만 새 모델로 교체 |
| `urgency.py`가 candidates 앱에서도 호출 | 외부 호출부 영향 없도록 반환 타입 유지 |
| `news/matcher.py`의 정규표현식 / 텍스트 매칭 로직이 복잡 | 상태 필드만 교체, 로직 본문은 건드리지 않음 |

## 7. 커밋 포인트

```
chore(projects): clean up legacy ProjectStatus/Contact/Offer refs in services

- Delete services/lifecycle.py entirely
- Rewrite services/dashboard.py with ActionItem-based aggregations
- Update services/auto_actions.py to suggest (not create) initial actions
- Rewrite services/submission.py for ActionItem 1:1 relationship
- Remove ProjectStatus refs from collision/urgency/approval/news/matcher
- ruff clean, manage.py check passing at services layer

Refs: FINAL-SPEC.md §2, §3
```

## 8. Phase 3a로 넘기는 인터페이스

- 모든 서비스 함수가 새 모델 기반으로 동작
- `get_today_actions(user)`, `get_overdue_actions(user)`, `get_upcoming_actions(user)`, `get_project_kanban_cards(organization)` signature 확정
- `application_lifecycle.drop/restore/hire` signature 확정
- `action_lifecycle.create_action/complete_action/skip_action/reschedule_action/propose_next` signature 확정
- Phase 3a의 forms·urls·메인 뷰가 이 서비스 함수만 호출하면 됨

---

**이전 Phase**: [phase-2a-services-core.md](phase-2a-services-core.md)
**다음 Phase**: [phase-3a-views-base.md](phase-3a-views-base.md)
