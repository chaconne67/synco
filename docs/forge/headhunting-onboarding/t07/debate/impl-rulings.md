# Task 7 구현담금질 쟁점 판정 결과

**Status:** COMPLETE
**Rounds:** 1
**Total Issues:** 7

---

## Accepted Items

### I-R1-01 [CRITICAL] 조직 관리 메뉴 URL 미존재 + 후속 태스크 경로 충돌
- **Source:** Codex C1 + Gemini G1
- **Decision:** ACCEPTED
- **Action:** 조직 관리 메뉴 항목을 t07에서 제거. t15/t17에서 URL과 함께 추가.
- **Impact on plan:** Step 1에서 조직 관리 메뉴 추가 제거, updateSidebar()의 organization key 추가 제거

### I-R1-03 [MAJOR] 네비게이션 필터링 검증 테스트 부재
- **Source:** Codex C3
- **Decision:** ACCEPTED
- **Action:** owner/consultant별 메뉴 노출/비노출 검증 테스트 추가 (Step 1.5)

### I-R1-04 [MINOR] 전체 교체 지시로 기존 동작 보존 누락 + 승인 메뉴 조건 조합 + 이름 변경 범위
- **Source:** Codex C4 + Gemini G2
- **Decision:** ACCEPTED
- **Action:** 최소 diff 기준으로 변경. 보존할 기존 동작 명시. 이름 변경은 nav-only로 한정

## Rebutted Items (Disputed → Closed)

### I-R1-02 [MAJOR] 레퍼런스 owner-only는 UI만, 서버 권한 미변경
- **Source:** Codex C2 + Gemini G1
- **Decision:** REBUTTED
- **Reasoning:** t07은 UI 필터링만 담당. 설계서가 "view 단 접근 제어(t05)와 별개" 명시. t05 확정 구현계획서에서 레퍼런스 read views는 @membership_required로 결정. 보안이 아닌 UX 정리.
- **Evidence:** design-spec.md line 10, t05/impl-plan-agreed.md

### I-R1-05 [MAJOR] updateSidebar() organization key null 참조 가능성
- **Source:** Gemini G3
- **Decision:** REBUTTED
- **Reasoning:** updateSidebar()는 querySelectorAll('.sidebar-tab').forEach로 순회하므로 존재하지 않는 요소에 접근하지 않음. getElementById 패턴이 아님. 또한 I-R1-01 수용으로 organization 추가 자체가 불필요.
- **Evidence:** nav_sidebar.html lines 71-84

### I-R1-06 [MINOR] 하드코딩된 역할 문자열 확장성
- **Source:** Gemini G4
- **Decision:** REBUTTED
- **Reasoning:** 현재 2개 역할 체계에서 YAGNI. 코드베이스 전체가 동일 패턴 사용 (decorators.py 포함). 역할 추가 시 일괄 리팩터링이 적절.

### I-R1-07 [MINOR] 모바일 nav에서 프로젝트 승인 메뉴 표시 여부 미정의
- **Source:** Gemini G5
- **Decision:** REBUTTED
- **Reasoning:** nav_bottom.html에 프로젝트 승인 메뉴 자체가 없음. 해당 사항 없음.
- **Evidence:** nav_bottom.html lines 1-68
