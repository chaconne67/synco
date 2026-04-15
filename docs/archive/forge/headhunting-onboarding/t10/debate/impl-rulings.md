# Impl Rulings — t10 (전체 통합 검증)

**Status:** COMPLETE
**Rounds:** 1
**Total Issues:** 9 (Accepted: 6, Rebutted: 3, Escalated: 0)

---

## Accepted Items

### I-R1-01 [CRITICAL] — Migration check incomplete
**Resolution:** Add `uv run python manage.py migrate --check` to Step 3. The existing `makemigrations --check --dry-run` only verifies model-migration file consistency, not DB schema synchronization.

### I-R1-02 [CRITICAL] — Consultant project detail/edit direct-URL bypass not verified
**Resolution:** Add checklist items verifying consultant cannot access unassigned project detail/edit by direct URL. Expected to reveal a Phase 1 implementation gap that will need follow-up fix.

### I-R1-04 [MAJOR] — Step 10 sidebar not reproducible
**Resolution:** Add precondition to create a pending approval project before verifying the "프로젝트 승인" sidebar label.

### I-R1-05 [MAJOR] — Task 9 empty-state CTAs not verified
**Resolution:** Add checklist items for role-based empty-state CTAs on dashboard, project list, and client list for both owner and consultant roles.

### I-R1-06 [MINOR] — No negative-path invite code testing
**Resolution:** Add one negative-path checklist item (invalid code → error message). Downgraded from MAJOR since automated tests already cover edge cases.

### I-R1-09 [MINOR] — No state transition lifecycle verification
**Resolution:** Add state transition checks: approved user re-visiting /accounts/pending/ → redirect to dashboard. Rejected user re-login → rejection screen.

---

## Rebutted Items (Disputed → Closed)

### I-R1-03 [CRITICAL → MINOR] — Reference management owner access
**Author's rebuttal:** t05's confirmed implementation plan explicitly states "Write views keep existing @staff_member_required (staff→role 전환은 별도 작업)." This is a known deferred item, not in Tasks 3-9 scope, and therefore not in t10's verification scope.
**Verdict:** Rebutted. Not a verification gap — a deliberate scope boundary.

### I-R1-07 [MAJOR → MINOR] — Unauthenticated access testing
**Author's rebuttal:** All views use `@login_required` (Django built-in). Automated test suite includes unauthenticated redirect tests. Manual verification adds no value.
**Verdict:** Rebutted. Covered by automated tests.

### I-R1-08 [MINOR] — Test coverage verification
**Author's rebuttal:** No coverage baseline exists in the project. Coverage tooling is a project-level concern, not a verification checklist item. Each task wrote its own tests.
**Verdict:** Rebutted. Out of scope for this verification task.
