# Phase 5 — 테스트 + Seed 데이터

**전제**: Phase 4 완료. 모든 뷰/템플릿이 렌더링 가능.
**목표**: 핵심 비즈니스 로직(phase 파생, ActionItem lifecycle, HIRED 자동 종료)과 뷰 플로우를 단위 테스트·통합 테스트로 덮는다. 선택적으로 엑셀 기반 seed 데이터 명령어 제공.
**예상 시간**: 0.5-1일
**리스크**: 낮음

---

## 1. 목표 상태

- `projects/tests/` 디렉터리에 새 테스트 파일 추가:
  - `test_phase_derivation.py` — compute_project_phase 규칙 검증
  - `test_application_lifecycle.py` — drop/restore/hire 서비스
  - `test_action_lifecycle.py` — create/complete/skip/propose_next
  - `test_signals.py` — post_save signal 동작 (phase, HIRED)
  - `test_views_dashboard.py` — 대시보드 뷰 플로우
  - `test_views_project.py` — 칸반·상세 뷰
  - `test_views_application.py` — Application CRUD 엔드포인트
  - `test_views_action.py` — ActionItem CRUD 엔드포인트
- `pytest` 전체 통과
- (선택) `management/commands/seed_action_types.py` — 개발용 seed 데이터 재주입 커맨드
- (선택) `management/commands/seed_from_excel.py` — 엑셀 1개 탭을 파싱해서 샘플 Project/Application/ActionItem 생성 (QA 용도)

## 2. 사전 조건

- Phase 4 커밋 완료
- 모든 서비스 함수와 signal이 동작
- 템플릿이 렌더 가능

## 3. 영향 범위

### 3.1 신규 파일
- `projects/tests/test_phase_derivation.py`
- `projects/tests/test_application_lifecycle.py`
- `projects/tests/test_action_lifecycle.py`
- `projects/tests/test_signals.py`
- `projects/tests/test_views_dashboard.py`
- `projects/tests/test_views_project.py`
- `projects/tests/test_views_application.py`
- `projects/tests/test_views_action.py`
- (선택) `projects/management/commands/seed_action_types.py`
- (선택) `projects/management/commands/seed_from_excel.py`

### 3.2 수정 파일
- `projects/tests/conftest.py` — 공용 픽스쳐 (User, Organization, Project, ActionType)
- 기존 `projects/tests/` 하위 테스트 중 ProjectStatus/Contact/Offer 참조 제거·삭제

## 4. 태스크 분할

### T5.1 — conftest.py 공용 픽스쳐
**파일**: `projects/tests/conftest.py`
**작업**:
```python
import pytest
from django.contrib.auth import get_user_model
from projects.models import ActionType, Project, Application

User = get_user_model()

@pytest.fixture
def organization(db):
    from accounts.models import Organization
    return Organization.objects.create(name="Test Org")

@pytest.fixture
def consultant(db, organization):
    user = User.objects.create_user(email="park@test.com", password="x")
    user.organization = organization
    user.save()
    return user

@pytest.fixture
def client_company(db, organization):
    from clients.models import Client
    return Client.objects.create(name="Samsung Electronics", organization=organization)

@pytest.fixture
def project(db, organization, client_company, consultant):
    p = Project.objects.create(
        title="AI Engineer",
        client=client_company,
        organization=organization,
        created_by=consultant,
    )
    p.assigned_consultants.add(consultant)
    return p

@pytest.fixture
def candidate(db):
    from candidates.models import Candidate
    return Candidate.objects.create(name="김철수", birth_year=1992)

@pytest.fixture
def application(db, project, candidate, consultant):
    return Application.objects.create(
        project=project, candidate=candidate, created_by=consultant
    )

@pytest.fixture
def action_types_seeded(db):
    """Seed migration에 의해 이미 존재해야 하지만, 명시적 fixture로도 제공."""
    from projects.management.commands.seed_action_types import Command
    Command.run_seed()
    return ActionType.objects.all()
```

---

### T5.2 — Phase 파생 규칙 테스트
**파일**: `projects/tests/test_phase_derivation.py`
**테스트 케이스** (FINAL-SPEC §3.1 기반):
1. 빈 프로젝트 → `searching`
2. Application 1건 (ActionItem 없음) → `searching`
3. ActionItem `reach_out` pending → `searching`
4. ActionItem `reach_out` done → `searching` (submit_to_client 아님)
5. ActionItem `submit_to_client` pending → `searching`
6. ActionItem `submit_to_client` done → `screening`
7. 해당 Application 드롭 → `searching`으로 재계산
8. 다른 Application의 `submit_to_client` 존재 → `screening` 유지
9. closed_at 세팅된 프로젝트 → phase 재계산 스킵 (마지막 값 유지)
10. 신규 Application 추가 (submit 안 된 것) + 기존 submit된 것 존재 → `screening` 유지 (OR 규칙)

**예시**:
```python
def test_phase_searching_when_no_submit(application, action_types_seeded):
    reach_out = ActionType.objects.get(code="reach_out")
    ActionItem.objects.create(
        application=application,
        action_type=reach_out,
        title="연락",
        status=ActionItemStatus.PENDING,
    )
    application.project.refresh_from_db()
    assert application.project.phase == ProjectPhase.SEARCHING

def test_phase_screening_when_submit_done(application, action_types_seeded, consultant):
    submit_type = ActionType.objects.get(code="submit_to_client")
    item = ActionItem.objects.create(
        application=application,
        action_type=submit_type,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert application.project.phase == ProjectPhase.SCREENING
```

---

### T5.3 — Application lifecycle 테스트
**파일**: `projects/tests/test_application_lifecycle.py`
**테스트 케이스**:
1. `drop(app, reason, actor, note)`:
   - `dropped_at` 세팅
   - `drop_reason`, `drop_note` 세팅
   - 기존 pending ActionItem들이 cancelled로 바뀜
   - phase 재계산 (필요 시)
2. `restore(app, actor)`:
   - `dropped_at`, `drop_reason`, `drop_note` 초기화
   - phase 재계산
3. `hire(app, actor)`:
   - `hired_at` 세팅
   - signal이 프로젝트 자동 종료 (closed_at, result=success)
   - 나머지 활성 Application 전원 드롭 (drop_reason=other)
4. HIRED 중복 처리:
   - 이미 closed 상태에서 두 번째 hire 호출 → warning 로그 + 변화 없음
5. Application drop 후 재매칭 (동일 project+candidate 조합):
   - Unique constraint 검증

---

### T5.4 — ActionItem lifecycle 테스트
**파일**: `projects/tests/test_action_lifecycle.py`
**테스트 케이스**:
1. `create_action(app, type, actor)`:
   - ActionItem 생성, status=pending, assigned_to=actor
   - title 자동 생성
2. `complete_action(action, actor, result)`:
   - status=done, completed_at 세팅, result 저장
3. `skip_action(action, actor)`:
   - status=skipped
4. `cancel_action(action)`:
   - status=cancelled
5. `reschedule_action(action, new_due_at)`:
   - due_at 업데이트
6. `propose_next(action)`:
   - 완료된 액션이 아니면 빈 리스트
   - 완료된 경우 `action_type.suggests_next` 기반 목록 반환
   - is_active=False인 타입은 제외
7. `is_overdue` property:
   - pending + due_at 과거 → True
   - done + due_at 과거 → False (완료됨)

---

### T5.5 — Signal 동작 테스트
**파일**: `projects/tests/test_signals.py`
**테스트 케이스**:
1. Application 생성 시 phase 재계산 트리거
2. ActionItem 저장 시 phase 재계산 트리거
3. ActionItem 삭제 시 phase 재계산 (submit된 것이 삭제되면 searching으로 복귀)
4. Application.hired_at 세팅 시:
   - 프로젝트 closed_at, result, note 자동 업데이트
   - 다른 활성 Application 전원 드롭
   - 두 번째 HIRED 시 warning (로그 확인)
5. Project.closed_at ↔ status 동기화:
   - closed_at 세팅 → status=closed
   - closed_at=None → status=open

---

### T5.6 — 대시보드 뷰 테스트
**파일**: `projects/tests/test_views_dashboard.py`
**테스트 케이스**:
1. 인증 안 된 사용자 → login redirect
2. 인증된 사용자 → 200 OK
3. 응답 컨텍스트에 `today_actions`, `overdue_actions`, `upcoming_actions` 포함
4. 다른 조직의 액션은 노출되지 않음
5. assigned_to가 본인인 액션만 노출
6. `/dashboard/todo/` HTMX partial → 부분 HTML 반환

---

### T5.7 — 프로젝트 뷰 테스트
**파일**: `projects/tests/test_views_project.py`
**테스트 케이스**:
1. `/projects/` GET → 200, 3컬럼 칸반 렌더
2. 필터(phase=searching) → 해당 프로젝트만
3. 필터(deadline_range=임박) → 해당 프로젝트만
4. `/projects/<id>/` GET → 상세 렌더
5. `/projects/<id>/close/` POST → 프로젝트 종료
6. `/projects/<id>/reopen/` POST → 재오픈
7. 권한: 다른 조직 프로젝트 접근 시 404 또는 403

---

### T5.8 — Application 뷰 테스트
**파일**: `projects/tests/test_views_application.py`
**테스트 케이스**:
1. `/projects/<id>/add_candidate/` POST (candidate_id) → Application 생성
2. 중복 매칭 시도 → 에러 응답
3. `/applications/<id>/drop/` POST → drop 처리
4. `/applications/<id>/restore/` POST → 드롭 취소
5. `/applications/<id>/hire/` POST → HIRED 처리 + 프로젝트 자동 종료
6. 권한 검증

---

### T5.9 — ActionItem 뷰 테스트
**파일**: `projects/tests/test_views_action.py`
**테스트 케이스**:
1. `/applications/<id>/actions/new/` POST → 생성
2. `/actions/<id>/complete/` POST → 완료 + 후속 제안 반환
3. `/actions/<id>/skip/` POST → 건너뛰기
4. `/actions/<id>/reschedule/` POST → 새 due_at 적용
5. `/actions/<id>/propose_next/` POST → 선택한 action_type들로 새 ActionItem 생성 (parent_action 연결)
6. 권한: 본인 담당 Application의 액션만

---

### T5.10 — 기존 테스트 정리
**작업**:
```bash
grep -r "ProjectStatus\|Contact\|Offer" projects/tests/
```
- 결과에 나오는 기존 테스트 파일 중 재설계와 충돌하는 것을 수정 또는 삭제
- `test_lifecycle.py` 등 기존 phase 전이 테스트는 삭제
- 유지되는 테스트는 import 정리

---

### T5.11 — (선택) `seed_action_types` 관리 커맨드
**파일**: `projects/management/commands/seed_action_types.py`
**작업**:
- data migration과 동일한 seed 23개 주입 (재실행 가능)
- `--force`로 기존 삭제 후 재주입
- 개발 DB 리셋 후 유용

---

### T5.12 — (선택) `seed_from_excel` 관리 커맨드
**파일**: `projects/management/commands/seed_from_excel.py`
**작업**:
- `Search Status.xlsx`의 김현정 탭(가장 체계적) 일부를 파싱
- Project + Candidate + Application + ActionItem 샘플 데이터 생성
- `--consultant=김현정 --limit=10` 같은 옵션
- 운영 배포 전 제거

---

### T5.13 — 테스트 실행 + 통과 확인
**작업**:
```bash
uv run pytest projects/tests/ -v
```

**예상**: 전체 통과. 실패 시 해당 로직 수정 후 재실행.

**참고**: 기존 테스트 중 불필요한 것 제거 후에도 전체 pytest가 통과해야 함.

---

## 5. 검증 체크리스트

- [ ] `test_phase_derivation.py` 10개 케이스 전부 통과
- [ ] `test_application_lifecycle.py` 5개 케이스 통과
- [ ] `test_action_lifecycle.py` 7개 케이스 통과
- [ ] `test_signals.py` 5개 케이스 통과
- [ ] 뷰 테스트 4개 파일 모두 통과
- [ ] `pytest projects/tests/ -v` 전체 통과
- [ ] 기존 테스트에서 ProjectStatus/Contact/Offer 참조 0건
- [ ] `seed_action_types` 커맨드 실행 시 23개 행 재생성 (선택)

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| signal 재귀로 테스트 무한 루프 | Phase 2에서 검증된 signal을 그대로 사용. 테스트에서 `mute_signals` 불필요 |
| 픽스쳐가 organization/client 의존성 복잡 | conftest.py에 공용 픽스쳐 모으기 |
| ActionType seed가 테스트 DB에 없음 | data migration은 테스트 DB에도 자동 적용되므로 문제 없음. fixture에서 명시적으로 확인만 |
| HTMX partial 응답 검증 | `response.content`에 특정 HTML 조각 포함 확인 또는 `pytest-django` `client.get` 사용 |
| View 테스트에서 로그인 필요 | `client.force_login(user)` 사용 |

## 7. 커밋 포인트

```
test(projects): cover ActionItem-based workflow

- Add test_phase_derivation.py (10 scenarios)
- Add test_application_lifecycle.py (drop/restore/hire)
- Add test_action_lifecycle.py (create/complete/skip/propose_next)
- Add test_signals.py (phase recompute + HIRED auto-close)
- Add view tests for dashboard/project/application/action endpoints
- Remove legacy tests referencing ProjectStatus/Contact/Offer
- Add seed_action_types management command

Refs: FINAL-SPEC.md §6
```

## 8. Phase 6로 넘기는 인터페이스

- 핵심 로직이 테스트로 고정됨
- 이후 Phase 6 레거시 제거 작업 중에도 pytest 통과 상태 유지
- seed 커맨드로 개발 DB를 언제든 재생성 가능

---

**이전 Phase**: [phase-4b-templates-modals.md](phase-4b-templates-modals.md)
**다음 Phase**: [phase-6-cleanup.md](phase-6-cleanup.md)
