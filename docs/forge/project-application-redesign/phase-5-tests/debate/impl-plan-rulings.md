# impl-plan Rulings — phase-5-tests

**Status**: COMPLETE
**Rounds**: 1
**Date**: 2026-04-14

## Resolved Items

### R1-01 [CRITICAL] HIRED ownership: signal vs hire() service
- **Experts**: E1#4, E2#1, E3#1 (3명 일치)
- **Action**: ACCEPTED
- **Ruling**: 계획서가 HIRED 처리를 signal 책임으로 기술했으나, 실제 구현은 `hire()` 서비스가 프로젝트 종료, 패자 드롭, 액션 취소, phase 재계산을 모두 수행함 (`signals.py:1` "HIRED processing is owned by hire() service, not signals"). 두 번째 hire도 warning이 아닌 `ValueError`. HIRED 테스트를 `test_application_lifecycle.py`의 `hire()` 서비스 테스트로 이동. `test_signals.py`는 phase/status sync만 담당.

### R1-02 [CRITICAL] Test directory structure
- **Experts**: E1#1, E2#2 (2명 일치)
- **Action**: ACCEPTED
- **Ruling**: `projects/tests.py` 파일이 존재하여 `projects/tests/` 디렉토리 생성 불가. 루트 `conftest.py`의 `collect_ignore`가 대량 레거시 테스트를 무시 중. 새 테스트는 기존 `tests/` 루트에 배치. `projects/tests.py` 삭제 포함.

### R1-03 [CRITICAL] conftest fixtures 호환성
- **Experts**: E1#2, E1#3, E2#2 (2명 일치)
- **Action**: ACCEPTED
- **Ruling**: 계획서의 `user.organization = organization` 패턴이 실제 Membership 모델과 불일치. `seed_action_types` 관리 커맨드가 존재하지 않음 (seed는 migration `0002_seed_action_types.py`에서 수행). 기존 `tests/conftest.py` 패턴 재사용: `Membership.objects.create()`, `User.objects.create_user(username=...)`. ActionType은 migration seed를 신뢰하되, fixture에서 존재 확인만.

### R1-04 [CRITICAL ↑] Lifecycle guard/invalid-transition 테스트 누락
- **Experts**: E1#5, E3#5, E3#6 (2명 일치, MAJOR→CRITICAL 상향)
- **Action**: ACCEPTED
- **Ruling**: Application lifecycle (`drop/restore/hire`)과 ActionItem lifecycle (`create/complete/skip/cancel/reschedule`) 모두 정상 전이만 테스트. 실제 서비스의 가드 조건(already dropped, cannot drop hired, invalid drop_reason, restore on closed project, hire dropped/already hired/closed, create on inactive type/inactive app/closed project, non-pending transition)이 모두 누락. 파라미터화 테스트로 허용/금지 전이 매트릭스 추가.

### R1-05 [CRITICAL ↑] Permission/filter 기대치 불일치
- **Experts**: E1#7, E2#7 (2명 일치, MAJOR→CRITICAL 상향)
- **Action**: ACCEPTED
- **Ruling**: `deadline_range` 필터 구현 없음 → 계획에서 제거. Phase 3b+ CRUD 뷰에 `@login_required` 누락 → 테스트에서 unauthenticated 접근 시 동작 검증 추가. "본인 담당 액션만"은 실제로 조직 스코프 + `@membership_required` 수준 → 실제 권한 모델로 수정.

### R1-06 [MAJOR] View HTMX contract 미테스트
- **Experts**: E1#6
- **Action**: ACCEPTED
- **Ruling**: View 테스트가 200 OK 수준에 머뭄. GET modal, invalid POST 400, HX-Trigger, HX-Redirect, partial template 렌더링 검증 추가. 모든 endpoint에 대해 5분할 매트릭스까진 필요 없으나, 핵심 CRUD(drop/hire/action complete)는 HTMX 헤더 + 응답 포맷 assertion 포함.

### R1-07 [MAJOR] Signal 테스트 false positive 위험
- **Experts**: E2#3
- **Action**: ACCEPTED
- **Ruling**: "생성 시 phase 재계산 트리거" 수준의 테스트는 기본값이 이미 올바를 때 signal 없이도 통과 가능. stale state correction 패턴으로 변경: phase를 일부러 잘못된 값으로 설정 → 트리거 후 올바른 값으로 복원 확인.

### R1-08 [MAJOR] DB constraint/transaction 테스트 누락
- **Experts**: E2#4
- **Action**: ACCEPTED
- **Ruling**: CheckConstraint(`project_open_implies_no_closed_at` 등), UniqueConstraint(`unique_application_per_project_candidate`, `unique_hired_per_project`) 위반 테스트 추가. `hire()`의 `select_for_update` 경로를 위한 `@pytest.mark.django_db(transaction=True)` 테스트 1개 추가.

### R1-09 [MAJOR] 기존 test_phase2a_services.py와 중복
- **Experts**: E2#5
- **Action**: PARTIAL
- **Ruling**: `tests/test_phase2a_services.py`(226줄, 16개 테스트)가 phase 파생, hire, drop, restore, create action 등을 이미 커버. 새 테스트는 이 기존 테스트를 **확장**하는 형태로 작성. 중복 테스트 금지. conftest 확장도 기존 `tests/conftest.py`에 추가. 단, 기존 테스트 파일의 구조를 변경하진 않음 — 새 파일에서 추가 시나리오만 커버.

### R1-10 [MAJOR] ORM query performance 테스트
- **Experts**: E2#6
- **Action**: PARTIAL
- **Ruling**: Phase 5 목표는 기능 정확성 테스트. 모든 endpoint에 `django_assert_num_queries` 적용은 scope creep. 단, 대시보드 칸반 경로는 N+1이 명확하므로 ONE query count smoke test 추가 (프로젝트 3개 기준 쿼리 수 상한 assertion). 종합 query budget은 별도 태스크로 분리.

### R1-11 [MAJOR] hire() 패자 pending ActionItem 취소 검증
- **Experts**: E3#2
- **Action**: ACCEPTED
- **Ruling**: `tests/test_phase2a_services.py:test_hire_closes_project_and_drops_others`가 이미 이 시나리오를 커버하지만, 패자 ActionItem이 `CANCELLED` 상태인지 명시적으로 assert. 추가로 대시보드에서 노출되지 않음을 검증.

### R1-12 [MAJOR] Full lifecycle integration test (§6.1)
- **Experts**: E3#3
- **Action**: ACCEPTED
- **Ruling**: 단위 테스트만으로는 상호작용 버그를 놓칠 수 있음. §6.1의 핵심 흐름(프로젝트 생성 → 후보 추가 → reach_out → submit → phase 전환 → hire → auto-close)을 1개 통합 테스트로 재현. 전체 시나리오 아닌 핵심 마일스톤만 검증.

### R1-13 [MAJOR] Case D: closed project reopen + add
- **Experts**: E3#4
- **Action**: ACCEPTED
- **Ruling**: §6.2 Case D 시나리오(종료 프로젝트에 후보 추가 시도 → 재개 → 추가) 테스트 추가. reopen 시 `result` 초기화, `status=open`, phase 재계산도 함께 검증.

### R1-14 [MINOR] Application post_delete phase recompute
- **Experts**: E3#7
- **Action**: ACCEPTED
- **Ruling**: `signals.py`가 `post_delete`도 수신하므로, submitted Application 삭제 시 `screening → searching` 전환 테스트 1개 추가.

## Summary

| Metric | Count |
|--------|-------|
| Total issues | 14 |
| Accepted | 11 |
| Partial | 2 |
| Rebutted | 0 |
| Escalated | 0 |
