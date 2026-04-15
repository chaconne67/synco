# Task 8: Implementation Tempering Rulings

**Status:** COMPLETE
**Rounds:** 1
**Models:** codex, gemini, agent (agent review consolidated into author analysis)

---

## Resolved Items

### I-R1-01 [CRITICAL] — Parameter name mismatch
**Ruling:** ACCEPTED. Plan must use `organization=` (not `org=`) throughout to match existing codebase.

### I-R1-02 [CRITICAL] — Step 4 overwrites collision approval workflow
**Ruling:** ACCEPTED. Step 4 must preserve both collision branches. Call `form.save_m2m()` after `project.save()`, remove existing `add(request.user)`, add default fallback only when no consultants selected.

### I-R1-03 [MAJOR] — Update view missing from plan
**Ruling:** ACCEPTED. Add Step 4.5 for `project_update`. Policy: update allows clearing all consultants (no default fallback). Form passes `organization=org` for queryset filtering.

### I-R1-04 [MAJOR] — Permission premise conflict
**Ruling:** ACCEPTED. `project_create` stays `@membership_required` per t05 ruling. Plan explicitly notes this. Design spec's "owner only" premise is overridden.

### I-R1-05 [MAJOR] — Tests too narrow
**Ruling:** PARTIAL. File placement (test_rbac.py) kept. Test scope expanded to 6 cases: owner assign, default, consultant create, collision path, update, negative.

### I-R1-06 [MAJOR] — No negative security tests
**Ruling:** ACCEPTED. Add cross-org user PK rejection test. `distinct()` unnecessary (OneToOneField).

### I-R1-07 [MINOR] — CheckboxSelectMultiple scalability
**Ruling:** REBUTTED. Current deployment scale is small. Design spec requires this widget. Not a plan-level change.
