# Task 5 구현담금질 쟁점 판정 결과

Status: COMPLETE
Rounds: 1
Models: codex-cli, gemini-api

---

## Accepted Items

### I-R1-01 [CRITICAL] — project_create owner-only breaks approval workflow
**ACCEPTED.** project_create를 owner-only로 잠그면 P11 충돌 승인 워크플로우가 끊김. project_create에는 `@membership_required`를 적용.

### I-R1-04 [MAJOR] — dashboard_actions/dashboard_team 누락
**ACCEPTED.** t04에서 명시적으로 t05 scope로 넘긴 항목. dashboard_actions → `@membership_required`, dashboard_team → `@role_required("owner")` 추가.

### I-R1-05 [MAJOR] — 인라인 _is_owner() 정리 누락
**ACCEPTED.** `@role_required("owner")` 적용 시 내부 인라인 `_is_owner()` 체크 제거.

### I-R1-06 [MAJOR] — --timeout=30 flag 사용 불가
**ACCEPTED.** `uv run pytest -v`로 변경. t04에서 수용된 이슈 재발.

### I-R1-08 [MINOR] — "나머지 모든 view" 모호한 표현
**ACCEPTED.** `@membership_required` 적용 대상 view 목록을 명시적으로 나열.

---

## Partial Items

### I-R1-02 [MAJOR] — Reference views 파일 경로 오류 + staff_member_required 충돌
**PARTIAL.** File Map에 `clients/views_reference.py` 추가 수용. 단, `@staff_member_required` → `@role_required("owner")` 전환 + 템플릿 `is_staff` 변경은 범위 초과. 읽기 뷰에 `@membership_required` 추가만 적용.

### I-R1-07 [MAJOR] — 통합 테스트 범위 부족
**PARTIAL.** 핵심 경로 대표 테스트 추가 (dashboard partials, project_delete, approval_queue). 모든 view x 모든 역할 조합은 과도.

---

## Rebutted Items

### I-R1-03 [MAJOR] — membership_required만으로는 "배정된 프로젝트만" 접근 제어 불가
**REBUTTED.** 프로젝트 배정 기반 필터링은 t06 ("프로젝트 목록 consultant 필터링")의 명시적 범위. t05는 데코레이터 적용만 담당. 사용자가 "다른 할일의 범위를 침범하면 해당 할일의 담금질이 무의미해진다"라고 명시적으로 제한.
