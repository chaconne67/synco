# impl-plan Rulings — t25

## Status: COMPLETE

## Resolved Items

### R1-01: Test 1 duplicates existing test [CRITICAL] — ACCEPTED
Remove `test_submission_create_form_validation_error_stays_in_form`. Replace with a genuinely new edge case.

### R1-02: Test 4 duplicates existing test [CRITICAL] — ACCEPTED
Remove `test_funnel_contacts_excludes_reserved`. Replace with a genuinely new edge case.

### R1-03: Test 2 missing interested_contact fixture [CRITICAL] — ACCEPTED
Add `interested_contact` fixture to `test_submission_create_duplicate_candidate_rejected`. Add assertion for Submission count staying at 1.

### R1-04: Step 3 expected test count wrong [MAJOR] — ACCEPTED
Correct test count to 19 (17 existing + 2 new after dedup).

### R1-05: Step 4 regression scope too narrow [MAJOR] — ACCEPTED
Expand Step 4 to include test_p07_submissions.py.

### R1-06: Test 2 should verify error message [MINOR] — ACCEPTED
Add assertion for specific validation error in duplicate test.

### R1-07: Tests should go in existing classes [MINOR] — REBUTTED
Cross-cutting integration edge cases belong in dedicated TestWorkflowEdgeCases class for organizational clarity and selective test execution.
