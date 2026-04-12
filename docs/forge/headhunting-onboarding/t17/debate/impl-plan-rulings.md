# impl-plan Rulings — t17

**Status:** COMPLETE
**Rounds:** 1

---

## Resolved Items

### R1-01 [CRITICAL] Mobile bottom nav layout overflow — ACCEPTED
Plan must address mobile layout overflow when adding 7th tab for owner. Adjust spacing/sizing approach.

### R1-02 [CRITICAL] No test cases for role-gated nav rendering — ACCEPTED
Add basic tests: owner sees org link, non-owner does not.

### R1-03 [MAJOR] Step 2 title contradicts body — ACCEPTED
Remove "replaces reference" wording. Intent is to add, not replace.

### R1-04 [MAJOR] --timeout=30 requires uninstalled pytest-timeout — ACCEPTED
Remove --timeout=30 from verification command. Use `uv run pytest -v`.

### R1-05 [MAJOR] Hardcoded URLs instead of {% url %} — REBUTTED
All existing nav links use hardcoded URLs. Introducing {% url %} for only org would be inconsistent. URL refactoring is a separate concern outside t17 scope.

### R1-06 [MAJOR] DRY violation — REBUTTED
Sidebar and mobile nav have different HTML structure and CSS classes by design. All existing items follow the same duplication pattern. This is the established codebase convention.

### R1-07 [MINOR] Position inconsistency — ACCEPTED
Clarify positioning to "before settings" consistently in both sidebar and mobile.
