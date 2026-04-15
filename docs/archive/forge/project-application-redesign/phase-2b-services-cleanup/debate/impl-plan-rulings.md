# impl-plan — 쟁점 판정 결과

**Status:** COMPLETE
**Rounds:** 1

## Resolved Items

### R1-02: ProjectStatus grep 검증 규칙 자기모순 [CRITICAL↑] — ACCEPTED
grep 검증 대상을 `ProjectStatus` 전체가 아닌 삭제된 레거시 멤버 패턴으로 한정.
검증 기준: `NEW|SEARCHING|RECOMMENDING|INTERVIEWING|NEGOTIATING|PENDING_APPROVAL|CLOSED_SUCCESS|CLOSED_FAIL|CLOSED_CANCEL|from .lifecycle|services.lifecycle`

### R1-05: lifecycle.py 삭제 시 voice/action_executor.py ImportError [CRITICAL] — ACCEPTED
lifecycle.py 즉시 삭제 불가. apply_interview_result 등을 action_lifecycle.py로 이동, legacy stub은 shim으로 유지, voice/ import 경로 업데이트.

### R1-07: get_today_actions/overdue 중복 [MAJOR] — ACCEPTED
get_today_actions에서 overdue 집합을 제외하여 중복 방지.

### R1-08: get_upcoming_actions scheduled_at 무시 [MAJOR] — ACCEPTED
scheduled_at OR due_at 조건으로 확장.

### R1-01: dashboard.py org 스코프 [CRITICAL] — PARTIAL (org 부분 ACCEPTED)
org 파라미터 추가. 기존 API 계약 파괴 주장은 REBUTTED — Phase 3 전면 재작성 예정이며, views.py lazy import이므로 import-time 오류 없음.

### R1-03: approval.py 수정 범위 [CRITICAL] — PARTIAL (구체 수정 ACCEPTED)
ProjectStatus.NEW → OPEN, contacts.exists() → applications.exists(). 별도 태스크 분리 주장은 REBUTTED — 기계적 치환 수준.

### R1-04: auto_actions.py 기존 API [CRITICAL↑] — PARTIAL (보존 명시 ACCEPTED)
기존 공개 API (get_pending_actions 등) 보존 명시. ACTION_DATA_SCHEMA 정리 주장은 REBUTTED — AutoAction 모델 재설계(Phase 6) 범위.

### R1-06: submission.py 소유권 공백 [CRITICAL] — REBUTTED
현재 submission.py는 Submission.Status 삭제로 이미 broken. 새 get_or_create_for_action()이 FINAL-SPEC 요구 반영. Orchestration은 Phase 3 view 로직.

## Disputed Items

없음.
