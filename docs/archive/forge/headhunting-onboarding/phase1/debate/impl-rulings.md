# Implementation Rulings: phase1 RBAC + Onboarding

**Status:** COMPLETE
**Rounds:** 2
**Total Issues:** 10 (CRITICAL: 2, MAJOR: 5, MINOR: 3)

---

## Accepted Items (applied to agreed impl plan)

### I-R1-01 [CRITICAL] _get_org not consolidated — ACCEPTED R1
Add `accounts/helpers.py` with consolidated `_get_org`. Replace both copies with imports. Add to File Map. Remove in-place modifications from Task 4 and Task 5.

### I-R1-02 [CRITICAL] Wrong field name `consultants` — ACCEPTED R1
Replace all `consultants` with `assigned_consultants` throughout the plan (Task 6, Task 8 tests, Task 8 form field, Task 8 view).

### I-R1-03 [MAJOR] Missing 'rejected' status — ACCEPTED R1
Add `REJECTED = "rejected"` to Status choices. Add rejected handling in decorator, view, template, URL, and tests.

### I-R1-04 [MINOR] Wrong import pattern in tests — ACCEPTED R1
Replace `__import__("django.test", ...)` with `from django.test import Client as TestClient` consistently.

### I-R1-05 [MAJOR] Form field name mismatch — ACCEPTED R1
Consequence of I-R1-02. Form field renamed to `assigned_consultants`.

### I-R1-06 [MAJOR] No explicit RunPython migration — PARTIAL R1
Add verification note: check auto-migration includes default, add RunPython if needed.

### I-R1-07 [MAJOR] "승인 요청" not renamed — ACCEPTED R1
Change sidebar text to "프로젝트 승인".

### I-R1-08 [MINOR] Stale design spec path — ACCEPTED R1
Update to `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`.

### I-R1-10 [MINOR] Redundant final commit — ACCEPTED R1
Remove Task 10 Step 5.

## Rebutted Items (not applied)

### I-R1-09 [MINOR] Anonymous user check in decorator — REBUTTED R1, WITHDRAWN R2
Consistent `@login_required` stacking makes the check unnecessary. Docstring note is sufficient.
