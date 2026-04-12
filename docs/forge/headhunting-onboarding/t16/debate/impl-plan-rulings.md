# Rulings — t16 impl-plan

## Status: COMPLETE

## Resolved Items

### I1: Form validation error display missing [CRITICAL → ACCEPTED]
- **Round:** 1
- **Resolution:** ACCEPTED. Add `{{ form.field.errors }}` and `{{ form.non_field_errors }}` to org_info.html and org_invites.html forms.

### I2: Tab bar uses buttons instead of links [CRITICAL → REBUTTED]
- **Round:** 1
- **Resolution:** REBUTTED. The existing `settings_tab_bar.html` uses identical `<button hx-get>` pattern. HTMX is a hard dependency in this project, not optional enhancement. Changing only org tabs to `<a>` while settings uses `<button>` would break consistency. Mutation forms follow the same convention as settings forms (hx-post without action attr).

### I3: Verification step lacks HTMX rendering tests [MAJOR → ACCEPTED]
- **Round:** 1
- **Resolution:** ACCEPTED. Add org-specific HTMX rendering tests mirroring `test_settings_tabs.py`: full-page with tab bar, HTMX main entry with tab bar, HTMX tab switch partial-only.

### I4: org_info.html missing success message [MINOR → ACCEPTED]
- **Round:** 1
- **Resolution:** ACCEPTED. Add `{% if message %}` block to org_info.html, consistent with org_members.html and org_invites.html.

### I5: Inconsistent feedback mechanism [MAJOR → REBUTTED]
- **Round:** 1
- **Resolution:** REBUTTED. Changing to HX-Trigger toast would require modifying views_org.py (out of t16 scope, which is template-only). Static message consumes what views provide. Toast is for client-side clipboard only — different feedback paths, not inconsistency.

### I6: Clipboard copy error handling [MAJOR → PARTIAL]
- **Round:** 1
- **Resolution:** PARTIAL (accepted as MINOR). Add Promise chaining for clipboard.writeText(). Severity remains MINOR — HTTPS in production and localhost both support clipboard API.
