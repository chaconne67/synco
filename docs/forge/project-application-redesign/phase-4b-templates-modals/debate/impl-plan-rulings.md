# Rulings — phase-4b-templates-modals impl-plan

**Status:** COMPLETE
**Rounds:** 1
**Red team:** Codex CLI (expert panel: HTMX/Frontend, Django Template/View, Data Model)
**Date:** 2026-04-14

## Resolved Items

### R1-01 [CRITICAL] Modal container hidden lifecycle — ACCEPTED
Modal container `hidden` class prevents content visibility. Plan must define open/close lifecycle.

### R1-02 [CRITICAL] No post-submit response contract — ACCEPTED
Each endpoint returns different response types. Plan must specify per-endpoint swap behavior.

### R1-03 [CRITICAL] project_close GET vs POST conflict — ACCEPTED
View is POST-only but template uses hx-get. Need GET handler for modal form.

### R1-04 [CRITICAL] action_complete/propose_next overlap — ACCEPTED
Remove next_action checkboxes from complete modal. Due_at in propose_next deferred (backend doesn't support).

### R1-05 [CRITICAL] Filter bar backend gap + phase/status confusion — ACCEPTED
종료 is status=closed, not phase. Either expand backend or reduce UI filters.

### R1-06 [CRITICAL] Wrong template target for candidate detail — ACCEPTED
Target must be `candidate_detail_content.html`, not `candidate_detail.html`.

### R1-07 [CRITICAL] N+1 optimization path incorrect — ACCEPTED
Use Prefetch() for reverse FK. Address current_state query pattern separately.

### R1-08 [MAJOR] action_skip/reschedule modals omitted — ACCEPTED
Include in scope. Views already exist, templates are stubs.

### R1-09 [MAJOR] Accessibility contract — PARTIAL
ACCEPTED: role="dialog", aria-modal, aria-labelledby, max-h+overflow, Escape key.
REBUTTED: Focus trap and inert — deferred to v2 (internal tool, <10 users).

### R1-10 [MAJOR] Timeline tab disabled — ACCEPTED
Enable tab and wire hx-get to timeline partial view.

### R1-11 [MAJOR] Partial views missing prefetch — ACCEPTED
Add explicit prefetch contract to partial views used by HX-Trigger reloads.

### R1-12 [MAJOR] action_items ordering — ACCEPTED
Specify ordering per partial: timeline uses -created_at, actions list uses status/due_at.

### R1-13 [MINOR] ProjectStatus in legacy grep — ACCEPTED
Remove ProjectStatus from grep check, target actual legacy artifacts only.

## Disputed Items

(None)
