# impl-plan Rulings — t20

**Status:** COMPLETE
**Rounds:** 1

---

## Resolved Items

### R1-01: Test fixture missing `interested_contact` + `owned_by` [CRITICAL] — ACCEPTED
SubmissionForm requires candidate with `owned_by=org` and Contact with `result=INTERESTED`. Plan's fixture lacks both. Fix: match test_p07 pattern.

### R1-02: Existing tests (test_p07) will break [CRITICAL] — ACCEPTED
`tests/test_p07_submissions.py` has multiple `assert resp.status_code == 204` assertions that will break. Plan must update these.

### R1-03: Step 4 self-contradictory [MAJOR] — ACCEPTED
Step 4 says both "remove hx-target" and "no change needed". Rewrite as clear no-op with explanation.

### R1-04: Code duplication with project_tab_submissions() [CRITICAL] — ACCEPTED
All 3 reviewers flagged. Call existing `project_tab_submissions()` instead of copying logic.

### R1-05: Weak tabChanged test — no JSON parsing [CRITICAL] — ACCEPTED
Parse JSON, verify `tabChanged.activeTab == "submissions"`, `submissionChanged` presence, and `HX-Reswap`.

### R1-06: `import json` inside function body [MAJOR] — ACCEPTED
Move to file top-level.

### R1-07: Line number inaccuracy [MINOR] — ACCEPTED
Correct "라인 1124" to actual line reference.

### R1-08: Fragile "추천 이력" string assertion [MAJOR] — REBUTTED
String is stable template heading, standard pattern to verify correct partial was rendered.

### R1-09: Missing HX-Reswap test [MINOR] — ACCEPTED
Add HX-Reswap assertion.

### R1-10: Overly split test methods [MINOR] — REBUTTED
Separate methods provide clearer failure diagnostics, consistent with project convention.

---

## Disputed Items

None — all items resolved in Round 1.
