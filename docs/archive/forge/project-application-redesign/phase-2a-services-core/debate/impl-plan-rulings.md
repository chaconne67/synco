# impl-plan Rulings — phase-2a-services-core

**Status:** COMPLETE (2 rounds, 13 issues, all resolved)

---

## Resolved Items

### I-01. CRITICAL — HIRED 자동 드롭 pending ActionItem 취소 누락 [ACCEPTED]
HIRED 전체 로직을 hire() 서비스로 이관. transaction.atomic() + select_for_update()로 감싸고, losers 드롭 시 drop() 호출 또는 pending ActionItem cancelled를 포함하는 bulk 처리.

### I-02. CRITICAL — 동시 hire race condition [ACCEPTED]
hire()에 select_for_update() 추가. DB-level partial UniqueConstraint(condition=Q(hired_at__isnull=False)) 추가.

### I-03. CRITICAL — result 미초기화 → DB 크래시 [ACCEPTED]
DB CheckConstraint `project_open_implies_empty_result`가 이미 존재하므로, sync_project_status_field에서 reopen 시 result=""를 같이 .update(). 안 하면 IntegrityError.

### I-04. MAJOR — on_application_hired 전이 미감지 [ACCEPTED]
I-01 해결(서비스 이관)로 자연 해소.

### I-05. MAJOR — drop() atomic 부재 [ACCEPTED]
transaction.atomic() 래퍼 추가.

### I-06. MAJOR — 자동 드롭 per-row save() [PARTIAL]
**수용:** per-row save()가 post_save signal 연쇄를 유발하는 문제 → bulk .update() + 명시적 phase 재계산 1회로 변경.
**미해결:** 성능 리스크 판정 (저자: 5~20명 규모에서 N+1 무시 가능)

### I-07. MAJOR — Application 상태 전이 불완전 [ACCEPTED]
drop/restore/hire 각 함수에 전이 가드 추가. 명시적 전이표 작성.

### I-08. MAJOR — ActionItem 상태 머신 미정의 [ACCEPTED]
create_action()에 application.is_active + project.closed_at 가드. 상태 전이 함수에 현재 status 검증 추가.

### I-09. CRITICAL — 테스트 위치/fixture 불일치 [ACCEPTED]
기존 tests/ 구조 유지 또는 projects/tests/conftest.py 명시. conftest 위치 확정.

### I-10. CRITICAL — 풀 스위트 회귀 미보장 [PARTIAL]
**수용:** Phase 2a 게이트에 `uv run pytest -v` 포함. 깨질 테스트를 문서에 명시하고 xfail/skip.
**미해결:** 레거시 테스트 근본 수정의 Phase 2a 포함 범위 (저자: Phase 2b/5 영역)

### I-11. MAJOR — Signal 테스트 미자동화 [ACCEPTED]
Phase 2a에 signal 통합 테스트 최소 4개 추가.

### I-12. MAJOR — 서비스 lifecycle 테스트 누락 [ACCEPTED]
Phase 2a에 서비스 DB 테스트 추가.

---

## Formerly Disputed Items (Round 2에서 해결)

### I-06 (성능 부분) — MAJOR [RESOLVED: Red team ACCEPT]
Round 2에서 레드팀이 수용. 5~20 규모에서 행 단위 업데이트 수 자체는 MAJOR 성능 이슈 아님. signal cascade 해결(bulk update)은 이미 합의.

### I-10 (레거시 수정 범위) — CRITICAL→PARTIAL [RESOLVED: Red team ACCEPT]
Round 2에서 레드팀이 수용. 레거시 참조가 Phase 2a 범위를 넘는 광범위 정리임을 코드로 확인. Phase 2a는 xfail/skip + green suite gate가 적절. 공용 fixture 정리는 I-09에서 별도 처리.

### I-13. MAJOR — ActionType seed 무결성 [RESOLVED: Author ACCEPT in R2]
Round 2에서 레드팀이 새 증거 제시: Django `QuerySet.get()` 예외 메시지는 `"ActionType matching query does not exist."` 고정이며 lookup kwargs를 포함하지 않음 (django/db/models/query.py:635 확인). 저자의 "코드명 포함" 반박 근거가 사실과 불일치. 별도 seed integrity test 추가 합의.
