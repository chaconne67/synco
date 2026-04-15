# Design Rulings — p16-work-continuity

Status: COMPLETE
Last updated: 2026-04-10T14:30:00Z
Rounds: 1

## Resolved Items

### Issue D-R1-01: Signal handlers use .delay() but no Celery [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** .delay() calls require Celery which is not in the stack. Signals must use synchronous service calls.
- **Action:** Replace all .delay() with direct service function calls that create AutoAction(status=pending) records.

### Issue D-R1-02: Missing context save endpoint [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** URL table missing POST endpoint for autosave.
- **Action:** Add POST /projects/<pk>/context/save/ with JSON body {last_step, pending_action, draft_data}.

### Issue D-R1-03: beforeunload + HTMX POST unreliable [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** beforeunload async requests are unreliable. Three-tier autosave needed.
- **Action:** Primary: periodic debounce every 30s. Fallback: navigator.sendBeacon() on unload. HTMX: htmx:beforeHistorySave for in-app nav.

### Issue D-R1-04: Result value mismatch (Korean vs English) [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Signal conditions must use enum constants, not hardcoded strings.
- **Action:** Use Contact.Result.INTERESTED, Interview.Result.PASSED, ProjectStatus.NEW.

### Issue D-R1-05: Resume logic undefined [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** No form restoration mechanism specified.
- **Action:** Define FORM_REGISTRY mapping form names to URL, template, kwargs. Resume via HX-Redirect with ?resume=<context_id>.

### Issue D-R1-06: ProjectContext collision [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** Uniqueness constraint needed, but single-active-context is acceptable for v1.
- **Action:** Add UniqueConstraint(project, consultant). Use update_or_create. Most recent action wins.

### Issue D-R1-07: Time-delayed triggers have no mechanism [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Need due_at field and management command for cron.
- **Action:** Add due_at to AutoAction. Add check_due_actions management command. Add Submission post_save signal.

### Issue D-R1-08: Synchronous AI in signals blocks HTTP [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** AI generation must not run in signal handlers.
- **Action:** Signals create AutoAction(status=pending) only. AI generation deferred to user demand or management command.

### Issue D-R1-09: No permission rules [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** All endpoints need access control.
- **Action:** Verify organization membership + consultant matching on all views.

### Issue D-R1-10: AutoAction missing audit fields [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Need accountability fields for multi-consultant projects.
- **Action:** Add created_by, applied_by, dismissed_by FK(User) fields.

### Issue D-R1-11: No JSON schema validation [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** Need per-type validation but full jsonschema library is overkill.
- **Action:** Define expected keys per type in constants dict. Simple Python dict validation in apply service.

### Issue D-R1-12: Signal duplicate firing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** post_save fires on every save, not just transitions.
- **Action:** Check for existing pending AutoAction before creating. Idempotent creation.

### Issue D-R1-13: Status check uses hardcoded string [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Use enum reference for consistency.
- **Action:** Use ProjectStatus.NEW instead of "new".

### Issue D-R1-14: AutoAction not using BaseModel [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** All models should extend BaseModel per project convention.
- **Action:** AutoAction extends BaseModel. Remove manual id/created_at fields.

### Issue D-R1-15: Apply not atomic [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Need transaction safety and idempotency.
- **Action:** transaction.atomic() + select_for_update(). Status precondition: only pending → applied.

### Issue D-R1-16: Apply semantics undefined [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Each action type needs defined apply behavior.
- **Action:** Add per-type apply semantics table (data schema, target model, mutation).

### Issue D-R1-17: Voice resume integration undefined [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** Integration points defined, but actual P14 code changes tracked separately.
- **Action:** Define context_resolver.get_active_context(), resume_context intent, action_executor handler. Mark as P14 integration point.

### Issue D-R1-18: Test criteria missing negative cases [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Need negative/edge case tests.
- **Action:** Add 403, duplicate, concurrent, AI failure, invalid data test criteria.

### Issue D-R1-19: Artifact list incomplete [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** List all endpoints.
- **Action:** Expand artifact list to include all 7 URL endpoints.

### Issue D-R1-20: No cleanup strategy [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** Filter pending by default, rely on updated_at for audit.
- **Action:** Default filter to pending. No separate cleanup for v1.

## Disputed Items

(None — all items resolved in Round 1)
