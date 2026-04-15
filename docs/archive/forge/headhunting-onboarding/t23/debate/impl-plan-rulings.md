# impl-plan Rulings — t23

## Status: COMPLETE

---

## Resolved Items

### R1-01 [CRITICAL] Step 5 "관심" 필터 구현이 선택으로 표시됨 — ACCEPTED
Step 5를 필수로 승격. "(선택)" 제거. 필터 동작 테스트 추가.

### R1-02 [CRITICAL] 테스트가 핵심 기능을 검증하지 못함 — ACCEPTED
테스트를 강화: hx-get 속성 검증, ?result=관심 포함 검증, 5개 단계 URL, interested 카운트 정확성, RESERVED 제외 검증.

### R1-03 [MAJOR] 하드코딩된 "관심" 문자열 vs 상수 — PARTIAL
테스트에서 `Contact.Result.INTERESTED` 상수 사용으로 변경. 템플릿은 Django 한계로 문자열 유지하되 뷰에서 화이트리스트 검증 추가.

### R1-06 [MAJOR] contactChanged 자동 새로고침 시 필터 유실 — ACCEPTED
File Map에 tab_contacts.html 추가. result_filter를 컨텍스트로 내려주고 hx-get URL에 포함.

### R1-08 [MINOR] result 쿼리 파라미터 유효성 검증 없음 — ACCEPTED
Contact.Result.values로 화이트리스트 검증 추가.

---

## Disputed Items

### R1-04 [MAJOR] 퍼널 contacts 카운트와 탭 뱃지 카운트 불일치
**Red team:** 같은 페이지에서 퍼널과 탭 뱃지의 컨택 수가 달라 혼란.
**Author rebuttal:** 퍼널은 "완료 건수", 탭 뱃지는 "전체 항목 수(예정 포함)"로 의미가 다름. _build_tab_context()는 t19 확정 범위. 탭 뱃지 변경은 t23 범위 외.

### R1-05 [MAJOR] 프로그레스 바 width 계산 overflow
**Red team:** count > 9이면 100% 초과하여 overflow.
**Author rebuttal:** 기존 코드의 패턴. t23의 범위는 퍼널 클릭 가능화이지 프로그레스 바 리팩토링이 아님.

### R1-07 [MINOR] `<a>` 태그에 href 없음
**Red team:** 접근성, HTMX 실패 시 동작 불가.
**Author rebuttal:** 기존 탭바도 href 없는 `<button>` 사용. 프로젝트 패턴과 일치.

### R1-09 [MINOR] 프로그레스 바에 관심 단계 누락
**Red team:** 퍼널 텍스트에 관심이 추가되었으나 프로그레스 바에는 없음.
**Author rebuttal:** 관심은 컨택의 하위 결과이지 독립 단계가 아님. 프로그레스 바에 추가하면 중복 계산.

### R1-10 [MINOR] 중복 SVG 화살표 코드
**Red team:** 같은 SVG 4회 반복.
**Author rebuttal:** 기존 코드와 동일 패턴. 리팩토링은 t23 범위 외.
