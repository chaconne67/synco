# Implementation Plan Rulings — t03

**Status:** COMPLETE
**Rounds:** 1
**Date:** 2026-04-12

---

## Resolved Items

### I-R1-01 [CRITICAL] Root URL routing mismatch — ACCEPTED
**Issue:** `main/urls.py`에서 `path("", dashboard)` 가 `path("", include("accounts.urls"))` 보다 먼저 매칭되어, `GET /`가 항상 `dashboard` 뷰로 진입. `home()` 뷰의 membership 상태별 라우팅이 동작하지 않음.
**Resolution:** `main/urls.py` 루트를 `accounts.views.home`으로 변경. dashboard는 `/dashboard/` 경로만 유지.

### I-R1-02 [CRITICAL] Pending user can re-submit invite code — ACCEPTED
**Issue:** `invite_code_page`의 guard에서 `pending` 상태를 처리하지 않아, pending 사용자가 POST 시 OneToOneField IntegrityError 500 발생.
**Resolution:** `invite_code_page` guard에 `pending` → `pending_approval` 리다이렉트 추가. 테스트 추가.

### I-R1-04 [MAJOR] Non-atomic invite code redemption — PARTIAL ACCEPT
**Issue:** `is_valid` 체크와 Membership 생성이 별도 쿼리로 비원자적.
**Resolution:** `transaction.atomic()` 블록으로 감싸기 수용. `select_for_update()`와 `InviteCode.use()` 변경은 현재 규모에서 과도하며 t01 범위 침범이므로 미수용.

### I-R1-05 [MAJOR] Consultant notification missing — ACCEPTED
**Issue:** design-spec의 "owner에게 알림 (웹 + 텔레그램)" 요구가 impl-plan에서 누락.
**Resolution:** 최소 구현 추가: consultant pending 생성 시 Notification 레코드 생성 + send_notification() 호출.

### I-R1-06 [MINOR] Commit step missing files — ACCEPTED
**Issue:** git add에 `tests/accounts/test_onboarding.py`와 수정된 `main/urls.py` 누락.
**Resolution:** 커밋 스텝에 누락 파일 포함.

---

## Disputed Items

### I-R1-03 [MAJOR] /dashboard/ direct access — REBUTTED
**Issue:** `/dashboard/` 직접 접근 시 non-active 사용자에게 404 발생.
**Author rebuttal:** t04 "dashboard 보호 + test fixture 업데이트"의 범위. forge-progress.json에서 t04가 t03에 의존하며 정확히 이 문제를 다룸. t03에서 처리하면 t04 범위 침범.
**Status:** 저자 반박 유지. t04에서 처리.
