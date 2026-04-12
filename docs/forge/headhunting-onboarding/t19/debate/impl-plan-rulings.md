# impl-plan — Rulings

**Status:** COMPLETE
**Rounds:** 2

---

## Resolved Items

### R1-01: tabChanged event is never dispatched [CRITICAL → PARTIAL]
**Round 1:** REBUTTED — Design spec scopes t19 as infrastructure only.
**Round 2:** Codex challenged: downstream tasks don't cover regular tab bar clicks. Gemini accepted rebuttal.
**Final:** PARTIAL — Gap is valid at project level, documented as upstream note. Not in t19's scope per design spec and batch constraint. Severity: MINOR for t19 (documentation note).

### R1-02: DOMContentLoaded fails on HTMX navigation [CRITICAL] → ACCEPTED
Plan must use htmx:afterSettle + readyState pattern like context-autosave.js.

### R1-03: Duplicate event listener registration on HTMX re-swap [MAJOR] → ACCEPTED
Plan must wrap in IIFE with cleanup logic, following context-autosave.js pattern.

### R1-04: project_delete() error path missing tab_latest [MAJOR] → ACCEPTED
Add tab_latest to project_delete() error path, ideally via shared helper.

### R1-05: Manual verification too weak [MAJOR] → ACCEPTED
Expand verification to test actual behavior: console dispatch, sessionStorage, badge rings.

### R1-06: Import style — local import inside function [MINOR] → ACCEPTED
Move Max to top-level import line 7.

### R1-07: offers missing from tab_latest [MINOR] → ACCEPTED
Add offers to tab_latest for consistency.

### R1-08: Line reference inaccuracy [MINOR] → ACCEPTED
Correct line references.

### R1-09: depends_on mismatch [MINOR] → ACCEPTED
Correct depends_on to t18.

---

## Disputed Items

None remaining.
