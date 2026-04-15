# Rulings — phase-6-cleanup impl-plan

**Status:** COMPLETE
**Rounds:** 1
**Red-team:** Codex CLI (expert panel: django-migration-safety, codebase-hygiene)

## Resolved Items

### R1-01: ProjectStatus를 레거시로 취급 [CRITICAL] — ACCEPTED
계획서가 ProjectStatus 전체를 제거 대상으로 명시했으나, OPEN/CLOSED 2-state enum은 활성. 제거된 10-state 멤버만 대상으로 수정.

### R1-02: 스캔 범위가 projects/만 [CRITICAL] — ACCEPTED
레포 전체 스캔(docs/, migrations/, .venv/ 제외)으로 확대. tests/, conftest.py, management commands 포함.

### R1-03: Management commands 미포함 [CRITICAL] — ACCEPTED
T6.9로 별도 태스크 추가. check_due_actions.py, send_reminders.py, telegram, voice services 포함.

### R1-04: 업그레이드 경로 미검증 [CRITICAL] — PARTIAL
`remove_stale_contenttypes --dry-run` 검증 추가 (수용). 전체 업그레이드 리허설은 Phase 6 범위 밖 (기각). deploy.sh 파이프라인이 이미 migration 검증 수행.

### R1-05: 템플릿 삭제 시 역참조 맵 없음 [CRITICAL] — ACCEPTED
T6.6에 역참조 스캔을 필수 선행으로 추가. dash_full.html 삭제 금지 (활성 사용 중).

### R1-06: makemigrations --check 게이트 누락 [MAJOR] — ACCEPTED
T6.10a로 별도 단계 추가. 검증 체크리스트에도 포함.

### R1-07: 레거시 데이터 페이로드 미처리 [MAJOR] — REBUTTED
코드 경로 제거로 old data는 inert. DB 테이블은 Phase 6에서 삭제하지 않으므로 data migration은 별도 단계로 분리가 안전.

### R1-08: Contact/Offer grep 패턴 불완전 [MAJOR] — ACCEPTED
`rg -n '\b(Contact|Offer)\b'`로 교체. 멀티라인 import 포함 전체 캐치.

### R1-09: 레거시 status 문자열 스캔 불완전 [MAJOR] — ACCEPTED
전체 10-state 제거 대상 목록으로 확대: new, searching, recommending, interviewing, negotiating, closed_success, closed_fail, closed_cancel, on_hold, pending_approval.

### R1-10: URL 정리 범위 미흡 [MAJOR] — ACCEPTED
T6.8 확장: reverse(), {% url %}, hx-get 역참조 분석 포함. 레거시 라우트명 스캔 추가.

## Summary

| Metric | Count |
|--------|-------|
| Total issues | 10 |
| CRITICAL | 5 |
| MAJOR | 5 |
| MINOR | 0 |
| Accepted | 8 |
| Rebutted | 1 |
| Partial | 1 |
| Escalated | 0 |
