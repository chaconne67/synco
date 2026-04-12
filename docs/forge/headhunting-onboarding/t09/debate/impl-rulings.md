# Implementation Plan Rulings — Task 9

**Status:** COMPLETE
**Rounds:** 1
**Issues:** 7 (CRITICAL: 2, MAJOR: 3, MINOR: 2)
**All Accepted:** 7/7

---

## Accepted Items

### I-R1-01 [CRITICAL] Project list targets wrong template
**Resolution:** Replace `view_board.html` with `view_list.html` and `view_table.html` in the File Map. Use correct context variables (`urgency_groups` for list, `page_obj` for table). Board view intentionally has no global empty state.

### I-R1-02 [CRITICAL] Dashboard empty state logic is infeasible
**Resolution:** Replace monolithic dashboard empty state with per-partial approach. Modify `dash_actions.html` and `dash_schedule.html` existing `{% else %}` blocks to show role-appropriate text using `is_owner` variable. Remove the single-condition `{% if not today_actions and not weekly_schedule %}` approach.

### I-R1-03 [MAJOR] Header buttons visible to consultants
**Resolution:** Wrap `+ 등록` header buttons in `{% if membership and membership.role == 'owner' %}` in both `project_list.html` and `client_list.html`.

### I-R1-04 [MAJOR] Design spec requires 5 screens, plan covers only 3
**Resolution:** Add `tab_contacts.html` and `tab_submissions.html` to File Map. Update empty state text to match design spec (role-independent).

### I-R1-05 [MAJOR] Client list breaks search-empty distinction
**Resolution:** Preserve existing `page_obj.object_list` / `q` branching. Add role-based CTA only in the `{% if not q %}` branch.

### I-R1-06 [MINOR] CTA markup lacks HTMX attributes
**Resolution:** All CTA links must include `hx-get`, `hx-target="#main-content"`, `hx-push-url="true"`. Use `{% url %}` for all URLs.

### I-R1-07 [MINOR] Dashboard pattern inconsistency
**Resolution:** Use `is_owner` for dashboard templates (subsumed by I-R1-02).

---

## Disputed Items

None.
