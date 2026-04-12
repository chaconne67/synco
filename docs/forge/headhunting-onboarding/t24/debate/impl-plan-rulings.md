# impl-plan Rulings — t24

## Status: COMPLETE

## Resolved Items

### R1-01 [CRITICAL] Manual verification Step 3.4 conflicts with known limitation — ACCEPTED
Regular tab clicks don't dispatch `tabChanged`. Step 3 must use a flow that dispatches `tabChanged` (funnel navigation or submission_create).

### R1-02 [CRITICAL] Tests only verify markup, not actual new-indicator behavior — ACCEPTED
Goal narrowed to "마크업 회귀 테스트(자동) + 동작 검증(수동)". Manual verification strengthened.

### R1-03 [CRITICAL] Assertions too loose — whole-page string search — ACCEPTED
Assertions strengthened to verify attributes within specific tab button contexts, not whole-page string search.

### R1-04 [MAJOR] Missing tabs in data-tab assertion (4 of 6) — ACCEPTED
All 6 tabs asserted: overview, search, contacts, submissions, interviews, offers.

### R1-05 [CRITICAL] No negative case — badge absent when count=0 — ACCEPTED
Added test for empty project verifying badge span is absent.

### R1-06 [MINOR] Manual verification lacks sessionStorage initialization — ACCEPTED
Added prerequisite: fresh incognito/private tab or sessionStorage clear.

## Disputed Items

(none)
