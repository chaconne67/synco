# P05 구현 쟁점 판정 결과

**Status:** COMPLETE
**Rounds:** 2
**Date:** 2026-04-08

---

## Issue 1: 서칭 탭 조직 격리
**Severity:** CRITICAL
**Verdict:** ACCEPT
**Resolution:** match_candidates()에서 build_search_queryset() 호출 후, 슬라이스 전에 `qs.filter(owned_by=organization)` 적용. P05 서칭 탭 뷰에서 반드시 organization 전달.

## Issue 2+3: 서칭 탭 실행 경로 + 컨택 예정 범위
**Severity:** MAJOR
**Verdict:** ACCEPT
**Resolution:** P05 서칭 탭 = 완전 읽기 전용. POST endpoint 없음, 외부 링크 없음. match_candidates() 결과 표시 + 기존 Contact 이력 표시만. "컨택 예정 등록"은 P06. 배지는 "컨택 이력"으로 표현.

## Issue 4: 면접/오퍼 queryset 경로
**Severity:** MAJOR
**Verdict:** ACCEPT
**Resolution:** Interview.objects.filter(submission__project=project), Offer.objects.filter(submission__project=project) 명시.

## Issue 5: 활동 로그 → 최근 진행 현황
**Severity:** MAJOR
**Verdict:** ACCEPT
**Resolution:** "활동 로그"를 "최근 진행 현황"으로 변경. Contact 최신 3건 + Submission 최신 2건만 표시. 리드 담당자, 담당자 추가 기능 제거.

## Issue 6: HTMX target
**Severity:** MINOR
**Verdict:** ACCEPT
**Resolution:** 문서의 hx-target="main"을 hx-target="#main-content"로 통일.

## Issue 7: 테스트 기준 보강
**Severity:** MAJOR
**Verdict:** ACCEPT
**Resolution:** 각 탭 URL에 login_required + org 격리 검증 추가. 서칭 탭 결과에서 타 조직 후보자 비노출 테스트 추가.

## Issue 8: /candidates/ 비격리 진입점
**Severity:** MAJOR (NEW in R2)
**Verdict:** ACCEPT
**Resolution:** 서칭 탭에서 /candidates/로 보내는 링크 제거. candidates 앱 자체의 격리 문제는 P05 범위 밖, 별도 추적.
