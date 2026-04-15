# Rulings — phase-4a-templates-core impl-plan

**Status:** COMPLETE
**Rounds:** 1
**Red-team:** Codex CLI (expert panel: django-template, htmx-frontend)

## Resolved Items

### R1-01 [CRITICAL] Template path + inheritance mismatch — ACCEPTED
Document must use `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}` pattern and correct view render paths (`projects/dashboard.html`, `projects/project_list.html`, `projects/project_detail.html`).

### R1-02 [CRITICAL] complete/skip hx-post vs modal GET — ACCEPTED
All action buttons (완료/건너뛰기/나중에) must use `hx-get` to open modal in `#modal-container`, not direct `hx-post`.

### R1-03 [CRITICAL] Wrong URL names + # placeholders — ACCEPTED
Fix: `project_edit` → `project_update`. Replace `#` placeholders with actual modal GET endpoints: `project_close`, `application_drop`.

### R1-04 [CRITICAL → PARTIAL] Swap boundary too small — ACCEPTED (partial)
Card-level self-swap removed by modal adoption. Document must define HX-Trigger refresh contract: which containers listen for `actionChanged`/`applicationChanged` events to refresh via partial GET.

### R1-05 [CRITICAL] Missing tab structure — ACCEPTED
project_detail must preserve tab shell (Applications/Timeline/JD tabs). Only Applications tab implemented in 4a; others as placeholder/disabled.

### R1-06 [MAJOR] hired_at state unhandled — ACCEPTED
application_card must handle 3 states: active / dropped / hired. Use `application.is_active` or explicit 3-way branch.

### R1-07 [MAJOR] N+1 performance misdiagnosis — ACCEPTED
Document must specify correct prefetch strategy. `current_state` requires `Prefetch("action_items", queryset=...)` with custom queryset. Card templates need `select_related("application__project__client", "application__candidate")`.

### R1-08 [MAJOR] Missing reschedule button — ACCEPTED
Add reschedule/나중에 button to `action_item_card.html`. `hx-get` modal trigger to `action_reschedule` endpoint.

### R1-09 [MAJOR] Navigation not HTMX-compatible — ACCEPTED
All core navigation links must include `hx-get + hx-target="#main-content" + hx-push-url="true"` for progressive enhancement.

### R1-10 [MAJOR] #modal-container duplicated — ACCEPTED
Remove `<div id="modal-container">` from project_detail.html. Use base template's existing container.

### R1-11 [MINOR] Missing empty state for pending actions — ACCEPTED
Add empty state message when Application has 0 pending actions: "진행 중 액션이 없습니다."

## Disputed Items

(None — all resolved in Round 1)
