# Rulings — impl-plan (Phase 3b Views CRUD)

**Status**: COMPLETE
**Rounds**: 1
**Date**: 2026-04-14

---

## Resolved Items

### I-01 [CRITICAL] Missing organization scoping — ACCEPTED
Use `@membership_required` + `_get_org(request)` + pass `organization=org` to ApplicationCreateForm. Consistent with existing codebase pattern.

### I-02 [CRITICAL] Race condition in check-then-create — PARTIAL
DB UniqueConstraint exists as safety net. Fix: replace exists()+create() with transaction.atomic()+IntegrityError catch.

### I-03 [CRITICAL] No service layer for Application creation — ACCEPTED
Create `create_application()` service function. Both web view and voice view must call it.

### I-04 [CRITICAL] No error handling for lifecycle exceptions — ACCEPTED
Wrap all service calls in try/except ValueError. Return 400/409 with error partial.

### I-05 [CRITICAL] Silent success on invalid form — ACCEPTED
Invalid form → return 400 with form errors. Don't render success card.

### I-06 [CRITICAL] action_propose_next lacks validation/transaction — ACCEPTED
Verify action.status==DONE, validate IDs against propose_next(), wrap in atomic().

### I-07 [CRITICAL] HTMX redirect breaks modal flows — ACCEPTED
Use HX-Redirect/HX-Trigger for HTMX requests. Keep redirect() for non-HTMX.

### I-08 [CRITICAL] Missing placeholder templates — ACCEPTED
Add task to create minimal placeholder partials for all rendered templates.

### I-09 [CRITICAL] Modal GET endpoints missing — ACCEPTED
Add GET method branches for views that need modal rendering (drop, complete, skip, reschedule, action_create).

### I-10 [MAJOR] No HX-Trigger strategy — ACCEPTED
Define applicationChanged, actionChanged trigger events. Emit from mutation endpoints.

### I-11 [CRITICAL] Incomplete legacy removal — PARTIAL
Remove/stub tab_contacts, tab_offers views. Update detail_tab_bar.html to hide tabs. Update tab_overview.html to remove links. Full template migration stays in Phase 4.

### I-12 [MAJOR] Voice service layer not addressed — PARTIAL
Expand T3b.7 to include action_executor.py and intent_parser.py. Remove/disable contact_record, contact_reserve, offer_create intents. Full migration to Application/ActionItem is future work.

### I-13 [MAJOR] Incorrect ProjectStatus grep criterion — ACCEPTED
Narrow grep criterion to Contact/Offer references only. ProjectStatus is a valid live enum.

### I-14 [CRITICAL] Weak verification/test plan — PARTIAL
Add basic smoke tests for error paths, org scoping, lifecycle errors, NoReverseMatch. Full test suite is Phase 5.

### I-15 [MINOR] Inconsistent GET/POST context in action_create — ACCEPTED
Use consistent form object on both paths.

### I-16 [CRITICAL] Response shape / HTMX contract — PARTIAL
Define response contracts as view docstrings/comments. Use HX-Trigger headers. Detailed hx-target/hx-swap wiring is Phase 4.

---

## Disputed Items

None — all items resolved in Round 1.
