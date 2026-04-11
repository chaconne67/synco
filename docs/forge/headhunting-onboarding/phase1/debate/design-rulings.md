# Design Rulings: phase1 RBAC + Onboarding

**Status:** COMPLETE
**Rounds:** 2
**Total Issues:** 9 (CRITICAL: 1, MAJOR: 5, MINOR: 3)

---

## Accepted Items (applied to agreed spec)

### D-R1-01 [MAJOR] Incorrect field name — ACCEPTED R1
Section 1.7 `consultants` → `assigned_consultants` to match actual Project model field.

### D-R1-02 [MAJOR] Duplicate _get_org — ACCEPTED R1
Consolidate `_get_org` from `projects/views.py` and `clients/views.py` into `accounts/helpers.py`. Both apps import from there.

### D-R1-03 [MAJOR] InviteCode brute-force — PARTIAL ACCEPTED R1
Clarified: code is 8 fully random alphanumeric chars, no fixed prefix. Rate limiting deferred to impl plan.

### D-R1-05 [CRITICAL] Missing Membership.status field — ACCEPTED R1
Added formal field definition: CharField, choices=[active, pending, rejected], default='active', migration with RunPython.

### D-R1-06 [MAJOR] Pending redirect loop — ACCEPTED R1
Replaced vague "미들웨어 또는 데코레이터" with concrete `membership_required` decorator specification. Exempt views are naturally excluded by not applying the decorator.

### D-R1-08 [MAJOR] Rejected user re-apply loop — ACCEPTED R1
Changed rejection behavior: `Membership.status='rejected'` instead of deletion. Rejected users see error message + logout button. Added 'rejected' to status choices.

### D-R1-09 [MINOR] 승인 요청 naming collision — ACCEPTED R1
Renamed existing project approval to "프로젝트 승인". Member approval handled within "조직 관리" page, no separate sidebar item.

## Rebutted Items (not applied)

### D-R1-04 [MINOR] OneToOneField multi-org — REBUTTED R1, WITHDRAWN R2
Single-org per user is intentional. Login flow prevents reaching invite screen when membership exists. Red team withdrew after reviewing the flow logic.

### D-R1-07 [MINOR] Mobile nav filtering — REBUTTED R1, WITHDRAWN R2
Security enforced at view/decorator level. Mobile nav refinement deferred to phase 2. Red team agreed this is polish, not design flaw.
