# Phase 5 — 테스트 + Seed 데이터 (Agreed)

**전제**: Phase 4 완료. 모든 뷰/템플릿이 렌더링 가능.
**목표**: 핵심 비즈니스 로직(phase 파생, ActionItem lifecycle, HIRED 자동 종료)과 뷰 플로우를 단위 테스트·통합 테스트로 덮는다.
**예상 시간**: 0.5-1일
**리스크**: 낮음

**단일 진실 소스**: docs/designs/20260414-project-application-redesign/FINAL-SPEC.md

---

## 1. 목표 상태

- `tests/` 루트 디렉토리에 새 테스트 파일 추가 (기존 `tests/conftest.py` 확장):
  - `tests/test_phase_derivation.py` — compute_project_phase 규칙 검증 (기존 test_phase2a_services.py 보완)
  - `tests/test_application_lifecycle.py` — drop/restore/hire 서비스 + HIRED 전체 처리
  - `tests/test_action_lifecycle.py` — create/complete/skip/cancel/reschedule/propose_next
  - `tests/test_signals.py` — phase recompute signal + status sync (HIRED 제외)
  - `tests/test_constraints.py` — DB CheckConstraint + UniqueConstraint
  - `tests/test_views_dashboard.py` — 대시보드 뷰 플로우 + 쿼리 smoke
  - `tests/test_views_project.py` — 칸반·상세 뷰
  - `tests/test_views_application.py` — Application CRUD 엔드포인트
  - `tests/test_views_action.py` — ActionItem CRUD 엔드포인트
  - `tests/test_lifecycle_scenario.py` — §6.1 통합 시나리오
- `uv run pytest -v` 전체 통과
- `projects/tests.py` 삭제 (projects/tests/ 디렉토리 블로킹 방지)
- 루트 `conftest.py`의 `collect_ignore` 중 수정 가능한 항목은 정리

## 2. 사전 조건

- Phase 4 커밋 완료
- 모든 서비스 함수와 signal이 동작
- 템플릿이 렌더 가능
- **기존 `tests/test_phase2a_services.py` (16개 테스트) 존재** — 중복 금지, 확장만

## 3. 영향 범위

### 3.1 신규 파일
- `tests/test_phase_derivation.py`
- `tests/test_application_lifecycle.py`
- `tests/test_action_lifecycle.py`
- `tests/test_signals.py`
- `tests/test_constraints.py`
- `tests/test_views_dashboard.py`
- `tests/test_views_project.py`
- `tests/test_views_application.py`
- `tests/test_views_action.py`
- `tests/test_lifecycle_scenario.py`

### 3.2 수정 파일
- `tests/conftest.py` — Phase 5용 픽스쳐 추가 (기존 패턴 유지)
- `conftest.py` (루트) — 수정 가능한 `collect_ignore` 항목 정리

### 3.3 삭제 파일
- `projects/tests.py` — 리다이렉트 코멘트만 포함, 불필요

## 4. 기존 테스트와의 관계

`tests/test_phase2a_services.py`가 이미 커버하는 시나리오:
- 빈 프로젝트 → searching
- submit_to_client done → screening
- closed project keeps phase
- hire → project closed + others dropped + pending actions cancelled
- reopen → result cleared
- drop → pending actions cancelled
- double drop raises
- restore blocked on closed project
- hire dropped raises
- create action on dropped raises
- complete → propose_next
- action_type seed integrity

**원칙**: 위 16개 테스트와 중복하는 테스트를 새로 작성하지 않는다. 새 테스트는 기존이 커버하지 않는 시나리오만 추가한다.

## 5. 태스크 분할

### T5.1 — conftest.py 픽스쳐 확장

**파일**: `tests/conftest.py` (기존 파일에 추가)

기존 픽스쳐를 그대로 유지하고, Phase 5에 필요한 추가 픽스쳐만 작성:

```python
# --- Phase 5 추가 픽스쳐 ---

@pytest.fixture
def action_type_reach_out(db):
    """Migration-seeded ActionType 가져오기."""
    from projects.models import ActionType
    return ActionType.objects.get(code="reach_out")

@pytest.fixture
def action_type_submit(db):
    from projects.models import ActionType
    return ActionType.objects.get(code="submit_to_client")

@pytest.fixture
def action_type_confirm_hire(db):
    from projects.models import ActionType
    return ActionType.objects.get(code="confirm_hire")

@pytest.fixture
def logged_in_client(client, user):
    """pytest-django client with force_login."""
    client.force_login(user)
    return client

@pytest.fixture
def other_org_client(client, other_org_user):
    """다른 조직 사용자로 로그인된 client."""
    client.force_login(other_org_user)
    return client
```

**핵심**: `user.organization = org` 패턴 사용 금지. 반드시 `Membership.objects.create()` 패턴 사용 (기존 conftest.py:17-20 참조). ActionType은 migration seed를 신뢰 — `get_or_create` 대신 `get(code=...)` 사용.

---

### T5.2 — Phase 파생 추가 테스트

**파일**: `tests/test_phase_derivation.py`

기존 `test_phase2a_services.py`가 커버하지 않는 케이스만 추가:

1. ActionItem `reach_out` pending → `searching` (reach_out은 submit이 아님)
2. ActionItem `reach_out` done → `searching` (submit_to_client 아님)
3. ActionItem `submit_to_client` pending → `searching` (pending이라 아직 미완)
4. 해당 Application 드롭 → `searching`으로 재계산 (기존 test_submitted_app_drop_reverts_to_searching 보완: multiple app 시나리오)
5. 다른 Application의 `submit_to_client` 존재 → `screening` 유지 (OR 규칙)
6. 신규 Application 추가 + 기존 submit된 것 존재 → `screening` 유지
7. **Application 삭제 시 phase 재계산** (post_delete signal 검증)

---

### T5.3 — Application lifecycle 테스트

**파일**: `tests/test_application_lifecycle.py`

**성공 경로** (기존 test_phase2a_services.py 미커버 시나리오만):

1. `create_application()` 정상 생성
2. `drop()` 후 `restore()` 전체 왕복
3. `hire()` 전체 처리 검증:
   - `hired_at` 세팅
   - 프로젝트 `closed_at`, `status=closed`, `result=success` 자동 업데이트
   - 나머지 활성 Application 전원 드롭 (`drop_reason=other`)
   - **패자 후보의 pending ActionItem 전원 `status=cancelled`** (R1-11)
   - phase 재계산 (`compute_project_phase` 호출)

**실패 경로 (guard 테스트)** — 파라미터화 권장:

4. `drop()`: already dropped → `ValueError`
5. `drop()`: hired application → `ValueError`
6. `drop()`: invalid drop_reason → `ValueError`
7. `restore()`: not dropped → `ValueError`
8. `restore()`: hired application → `ValueError`
9. `restore()`: closed project → `ValueError`
10. `hire()`: dropped application → `ValueError`
11. `hire()`: already hired → `ValueError`
12. `hire()`: closed project → `ValueError`
13. `hire()`: another app already hired in project → `ValueError`
14. `create_application()`: closed project → `ValueError`
15. `create_application()`: duplicate project+candidate → `ValueError`

---

### T5.4 — ActionItem lifecycle 테스트

**파일**: `tests/test_action_lifecycle.py`

**성공 경로**:

1. `create_action()`: 정상 생성, status=pending, assigned_to=actor, title 자동 생성
2. `complete_action()`: status=done, completed_at 세팅, result 저장
3. `skip_action()`: status=skipped, completed_at 세팅
4. `cancel_action()`: status=cancelled
5. `reschedule_action()`: due_at 업데이트
6. `propose_next()`: 완료된 액션 → action_type.suggests_next 기반 목록 반환
7. `propose_next()`: 미완료 액션 → 빈 리스트
8. `propose_next()`: is_active=False인 타입 → 제외
9. `is_overdue` property: pending + due_at 과거 → True
10. `is_overdue` property: done + due_at 과거 → False (완료됨)
11. `is_overdue` property: pending + due_at None → False

**실패 경로 (guard 테스트)**:

12. `create_action()`: inactive action_type → `ValueError`
13. `create_action()`: inactive application (dropped) → `ValueError`
14. `create_action()`: closed project → `ValueError`
15. `complete_action()`: non-pending → `ValueError`
16. `skip_action()`: non-pending → `ValueError`
17. `cancel_action()`: non-pending → `ValueError`
18. `reschedule_action()`: non-pending → `ValueError`

---

### T5.5 — Signal 동작 테스트

**파일**: `tests/test_signals.py`

**핵심 원칙**: HIRED 처리는 `hire()` 서비스가 소유 → 여기서 테스트하지 않음. Signal은 phase recompute + status sync만 담당.

**Phase recompute (stale state correction 패턴)**:

1. ActionItem 생성 시 phase 재계산:
   - Project.phase를 DB에서 일부러 `screening`으로 설정
   - submit이 아닌 ActionItem 생성 → phase 여전히 `searching`으로 교정됨
2. ActionItem 삭제 시 phase 재계산:
   - submitted ActionItem 삭제 → `screening` → `searching` 전환
3. Application 생성 시 phase 재계산 (smoke)
4. **Application 삭제 시 phase 재계산** — submitted Application 삭제 → `searching` 복귀

**Project status sync**:

5. `closed_at` 세팅 → `status=closed` 자동 sync
6. `closed_at=None` → `status=open`, `result=""` 자동 초기화

---

### T5.6 — DB Constraint 테스트

**파일**: `tests/test_constraints.py`

1. `unique_application_per_project_candidate`: 동일 project+candidate 두 번째 생성 시 `IntegrityError`
   - **주의**: 이 제약은 dropped 여부와 무관한 "무조건 유일" — drop 후 재매칭도 금지
2. `unique_hired_per_project`: 같은 프로젝트에서 두 번째 hired → `IntegrityError`
3. `project_open_implies_no_closed_at`: open 상태에서 closed_at 세팅 시 제약 위반
4. `project_open_implies_empty_result`: open 상태에서 result 세팅 시 제약 위반
5. `project_result_implies_closed`: result 있는데 open이면 제약 위반
6. `hire()` transaction 테스트: `@pytest.mark.django_db(transaction=True)` — `select_for_update` 경로 검증

---

### T5.7 — 대시보드 뷰 테스트

**파일**: `tests/test_views_dashboard.py`

1. 인증 안 된 사용자 → login redirect
2. 인증된 사용자 → 200 OK
3. 응답 컨텍스트에 `today_actions`, `overdue_actions`, `upcoming_actions` 포함
4. 다른 조직의 액션은 노출되지 않음
5. assigned_to가 본인인 액션만 노출
6. `/dashboard/todo/` HTMX partial → 부분 HTML 반환 (content type 확인)
7. **쿼리 수 smoke test**: 프로젝트 3개 + 각 Application 2개 상태에서 대시보드 렌더 시 쿼리 수 상한 assertion (`django_assert_num_queries` 또는 `CaptureQueriesContext`)

---

### T5.8 — 프로젝트 뷰 테스트

**파일**: `tests/test_views_project.py`

1. `/projects/` GET → 200, 칸반 렌더 (context에 cards 포함)
2. 필터(phase=searching) → 해당 프로젝트만 (실제 구현은 context에 phase_filter 전달, queryset 필터 아님 — 현재 동작 기준으로 테스트)
3. `/projects/<id>/` GET → 상세 렌더
4. `/projects/<id>/close/` POST → 프로젝트 종료, HX-Redirect 응답
5. `/projects/<id>/reopen/` POST → 재오픈, `result=""`, `status=open`
6. 권한: 다른 조직 프로젝트 접근 시 404
7. 인증 안 된 사용자 → login redirect

**참고**: `deadline_range` 필터는 현재 미구현 → 테스트 대상에서 제외.

---

### T5.9 — Application 뷰 테스트

**파일**: `tests/test_views_application.py`

**정상 경로**:
1. `/projects/<id>/add_candidate/` POST (candidate_id) → Application 생성
2. `/applications/<id>/drop/` POST → drop 처리, 204 + HX-Trigger 응답
3. `/applications/<id>/restore/` POST → 드롭 취소
4. `/applications/<id>/hire/` POST → HIRED 처리 + 프로젝트 자동 종료, HX-Redirect

**오류 경로**:
5. 중복 매칭 시도 → 에러 응답
6. 다른 조직 Application 접근 → 404
7. **인증 없이 접근**: unauthenticated → login redirect 또는 safe failure (Phase 3b 뷰의 @login_required 누락 확인)
8. invalid POST (빈 candidate_id) → 에러 응답 (500 아님)

**HTMX 계약**:
9. drop POST (HTMX 헤더 포함) → 204 + HX-Trigger 확인
10. hire POST → HX-Redirect 확인

---

### T5.10 — ActionItem 뷰 테스트

**파일**: `tests/test_views_action.py`

**정상 경로**:
1. `/applications/<id>/actions/new/` POST → 생성
2. `/actions/<id>/complete/` POST → 완료 + 후속 제안 반환
3. `/actions/<id>/skip/` POST → 건너뛰기
4. `/actions/<id>/reschedule/` POST → 새 due_at 적용
5. `/actions/<id>/propose_next/` POST → 선택한 action_type들로 새 ActionItem 생성

**오류/권한 경로**:
6. 다른 조직의 Action 접근 → 404
7. 인증 없이 접근 → safe failure
8. complete 시 invalid form → 에러 응답 (500 아님)

**HTMX 계약**:
9. complete POST (HTMX) → 적절한 응답 (HX-Trigger 또는 partial)
10. action_create GET → 모달 partial 렌더

---

### T5.11 — Full Lifecycle Integration Test (§6.1)

**파일**: `tests/test_lifecycle_scenario.py`

§6.1 핵심 마일스톤을 1개 테스트로 재현:

```
1. Project 생성 (searching, open)
2. 후보자 3명 Application 생성 → phase 그대로 searching
3. 1번 후보: reach_out → complete → submit_to_client → complete
   → phase = screening (OR rule 발동)
4. 2번 후보: reach_out → complete → drop(candidate_declined)
   → phase 그대로 screening (1번의 submit 존재)
5. 3번 후보: 신규 추가 (submit 없음) → phase 그대로 screening
6. 1번 후보: confirm_hire → hire()
   → project closed, result=success
   → 3번 후보 auto-dropped, pending actions cancelled
   → phase 유지 (closed project)
7. reopen → status=open, result="", closed_at=None
   → phase 재계산
```

추가 시나리오:

8. **Case D**: closed project에 후보 추가 시도 → `ValueError` → reopen → add_candidate 성공

---

### T5.12 — 기존 테스트 정리

**작업**:
```bash
grep -r "ProjectStatus\|Contact\|Offer" tests/ --include="*.py"
```
- `conftest.py`의 `collect_ignore` 목록 검토
- 수정 가능한 테스트는 import 정리하여 `collect_ignore`에서 제거
- 복구 불가한 테스트는 `collect_ignore` 유지 (Phase 6에서 일괄 정리)
- `projects/tests.py` 삭제

---

### T5.13 — 테스트 실행 + 통과 확인

**작업**:
```bash
uv run pytest -v
```

**예상**: 전체 통과. 실패 시 해당 로직 수정 후 재실행.

---

## 6. 검증 체크리스트

- [ ] `test_phase_derivation.py` 7개 케이스 전부 통과
- [ ] `test_application_lifecycle.py` 15개 케이스 통과 (성공 5 + 실패 10)
- [ ] `test_action_lifecycle.py` 18개 케이스 통과 (성공 11 + 실패 7)
- [ ] `test_signals.py` 6개 케이스 통과 (stale state correction 포함)
- [ ] `test_constraints.py` 6개 케이스 통과
- [ ] 뷰 테스트 4개 파일 모두 통과 (HTMX 계약 + 권한 + 오류 경로 포함)
- [ ] `test_lifecycle_scenario.py` 통합 테스트 통과
- [ ] `uv run pytest -v` 전체 통과
- [ ] 기존 테스트(`test_phase2a_services.py`)와 중복 0건
- [ ] `projects/tests.py` 삭제됨

## 7. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| signal 재귀로 테스트 무한 루프 | Phase 2에서 검증된 signal을 그대로 사용. `.update()`로 재귀 방지 |
| 픽스쳐가 organization/client 의존성 복잡 | 기존 `tests/conftest.py` 패턴 재사용 (Membership 기반) |
| ActionType seed가 테스트 DB에 없음 | data migration은 테스트 DB에도 자동 적용. fixture에서 `get(code=...)` |
| HTMX partial 응답 검증 | `response.content`에 특정 HTML 조각 포함 확인 + HX-* 헤더 assertion |
| View 테스트에서 로그인 필요 | `client.force_login(user)` 사용 |
| Phase 3b 뷰에 @login_required 누락 | 테스트에서 현재 동작 검증. 수정은 Phase 6 범위 |
| 기존 test_phase2a_services.py와 중복 | 새 테스트 작성 전 기존 커버리지 확인 |
| collect_ignore 테스트 복구 실패 | Phase 6에서 일괄 정리. Phase 5는 새 테스트만 전체 통과 보장 |

## 8. 커밋 포인트

```
test(projects): cover ActionItem-based workflow with guards and HTMX contract

- Add test_phase_derivation.py (phase OR rule edge cases)
- Add test_application_lifecycle.py (drop/restore/hire + guard failures)
- Add test_action_lifecycle.py (create/complete/skip + invalid transitions)
- Add test_signals.py (phase recompute + status sync, stale state pattern)
- Add test_constraints.py (CheckConstraint + UniqueConstraint)
- Add view tests with HTMX contract assertions and auth edge cases
- Add test_lifecycle_scenario.py (§6.1 full scenario + Case D)
- Remove projects/tests.py (dead redirect comment)
- Extend tests/conftest.py with Phase 5 fixtures

Refs: FINAL-SPEC.md §3, §6
```

## 9. Phase 6로 넘기는 인터페이스

- 핵심 로직이 테스트로 고정됨
- Phase 3b 뷰의 `@login_required` 누락 수정은 Phase 6 범위
- `conftest.py` `collect_ignore` 레거시 테스트 정리는 Phase 6 범위
- ORM query budget 종합 테스트는 별도 태스크
- 이후 Phase 6 레거시 제거 작업 중에도 pytest 통과 상태 유지

---

**이전 Phase**: phase-4b-templates-modals
**다음 Phase**: phase-6-cleanup

<!-- forge:phase-5-tests:impl-plan:complete:2026-04-14T21:55:00Z -->
