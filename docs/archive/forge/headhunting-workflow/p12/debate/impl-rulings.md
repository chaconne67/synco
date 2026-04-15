# Implementation Rulings — p12

Status: COMPLETE
Last updated: 2026-04-08T23:10:00+09:00
Rounds: 1
Mode: agent (codex output truncated, fallback to agent review)

## Resolved Items

### Issue 1: clients/admin.py not updated after model field changes [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** admin.py references `preference_tier` (CompanyProfileAdmin.list_display) and existing fields that will be removed. Admin will crash after migration.
- **Action:** Add Task 1.5 to update `clients/admin.py` — update list_display, list_filter, search_fields for all 3 reference model admins to match new schema.

### Issue 2: company_autofill view requires pk but needed on create form [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** The autofill view does `get_object_or_404(CompanyProfile, pk=pk)` but on the create form, no pk exists yet. Design spec says autofill works on create form too.
- **Action:** Change autofill to accept company name via POST body instead of requiring pk. URL changes to `/reference/companies/autofill/` (no pk). View reads `name` from request.POST.

### Issue 3: Task 4 placeholder views cause template/URL errors [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Task 4 creates reference_index.html that includes company/cert tab partials, but those templates and views don't exist until Tasks 5-6. The index page will crash if accessed during Task 4.
- **Action:** Create stub views and empty tab templates in Task 4. Or restructure to create all views/templates together. Choose: create minimal stubs for companies/certs in Task 4.

### Issue 4: aliases search via __icontains on JSONField is fragile [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** `Q(aliases__icontains=q)` on a JSONField searches the serialized JSON text. This technically works on PostgreSQL (matches "CPA" inside `["CPA", "..."]`) but could match partial strings and is semantically wrong.
- **Action:** Keep `__icontains` for now as it works practically for the use case (short alias tokens). Add a comment noting this is a text-search approximation. If precision is needed later, use `__contains` with a JSON list lookup or a dedicated alias table.

### Issue 5: CSV handler two-pass approach has subtle race condition [MINOR]
- **Resolution:** PARTIAL
- **Summary:** The validate-then-upsert two-pass approach could miss errors if `update_or_create` fails in the second pass after validation succeeds. Also, iterating the file twice is unnecessarily complex.
- **Action:** Simplify to single-pass: validate each row then immediately upsert within the same transaction. On any error, the atomic block rolls back everything. Remove the two-pass design.

### Issue 6: _render_reference_page always loads university data as fallback [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** The helper always loads university data even when the active tab should be companies or certs.
- **Action:** Make the helper tab-aware: load appropriate model data based on active_tab parameter.

## Disputed Items

(none — all resolved)
