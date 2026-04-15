# Implementation Rulings — p16-work-continuity

Status: COMPLETE
Last updated: 2026-04-10T16:00:00Z
Rounds: 1

## Resolved Items

### I-R1-01: Project fixture triggers signals [CRITICAL]
- **Resolution:** ACCEPTED
- **Action:** Change conftest project to SEARCHING status. Add separate new_project fixture.

### I-R1-02: apply_action no per-type mutations [CRITICAL]
- **Resolution:** ACCEPTED
- **Action:** Add type-specific dispatch with handlers per ActionType.

### I-R1-03: Resume doesn't pre-fill forms [CRITICAL]
- **Resolution:** ACCEPTED
- **Action:** Modify contact_create to detect ?resume= and pre-fill from ProjectContext.

### I-R1-04: JS not loaded, forms not annotated [CRITICAL]
- **Resolution:** ACCEPTED
- **Action:** Include JS in template, annotate forms with data-autosave attributes.

### I-R1-05: sendBeacon CSRF failure [CRITICAL]
- **Resolution:** ACCEPTED
- **Action:** Use fetch({keepalive:true}) instead of sendBeacon for unload handler.

### I-R1-06: validate_action_data never called [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Call before mutations in apply_action.

### I-R1-07: Signal idempotency scoped to pending [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Remove status from idempotency check.

### I-R1-08: Signals trigger on any save [MAJOR]
- **Resolution:** PARTIAL — mitigated by I-R1-07 fix.

### I-R1-09: UniqueConstraint migration may fail on duplicates [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Add RunPython data migration for deduplication.

### I-R1-10: 404 vs 403 for other-org [MAJOR]
- **Resolution:** REBUTTED — 404 matches codebase pattern (non-disclosure).

### I-R1-11: FORM_REGISTRY incomplete [MAJOR]
- **Resolution:** PARTIAL — fix unsafe lookup, add more forms later.

### I-R1-12: Due actions stay pending forever [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Mark actions applied after notification creation.

### I-R1-13: Notification idempotency too broad [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Include auto_action_id in callback_data for uniqueness.

### I-R1-14: Missing generator files [MAJOR]
- **Resolution:** PARTIAL — wire existing posting.py, stub others.

### I-R1-15: Missing negative tests [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Add form-encoded, resume prefill, cross-org, concurrent, invalid data tests.

### I-R1-16: validate_draft_data char vs byte length [MINOR]
- **Resolution:** ACCEPTED

### I-R1-17: Lint command order [MINOR]
- **Resolution:** ACCEPTED

### I-R1-18: Sub-skill instruction [CRITICAL from Codex]
- **Resolution:** REBUTTED — standard plan boilerplate, doesn't access skill files.

### I-R1-19: Task 9 underspecified [MAJOR]
- **Resolution:** ACCEPTED
- **Action:** Show exact view modification code.

## Disputed Items

(None)
