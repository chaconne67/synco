# Task 4: Implementation Plan — Tempering Rulings

**Status:** COMPLETE
**Rounds:** 1
**Models:** codex, gemini

---

## Accepted Items

### I-R1-01 [MAJOR] + I-R1-04 [CRITICAL] — Missing route-level regression tests
**Source:** codex (MAJOR), gemini (CRITICAL)
**Ruling:** ACCEPTED — Both models independently identified the same critical gap. The plan must include integration tests for all 4 membership states on `/dashboard/`.
**Action:** Add new test step with tests for no-membership, pending, rejected, and active users accessing `/dashboard/`.

### I-R1-02 [MAJOR] — Verification command uses unavailable --timeout flag
**Source:** codex
**Ruling:** ACCEPTED — `pytest-timeout` not in `pyproject.toml`. Command changed to `uv run pytest -v`.

### I-R1-06 [MINOR] — Fixture update justification incorrect
**Source:** gemini
**Ruling:** PARTIAL — Accept that the justification is wrong (model default already provides active). Keep the explicit status for code clarity. Reword justification.

## Disputed Items (Rebutted)

### I-R1-03 [MINOR] — Fixture normalization incomplete in dashboard test file
**Source:** codex
**Ruling:** REBUTTED — Design spec explicitly scopes fixture update to `tests/conftest.py` shared fixtures only. Dashboard-local fixtures in `test_p13_dashboard.py` are functionally correct via model default and outside this task's scope.

### I-R1-05 [MAJOR] — dashboard_actions and dashboard_team left unprotected
**Source:** gemini
**Ruling:** REBUTTED — t05 design spec explicitly covers all remaining views: "나머지 모든 view -- `@membership_required`". Adding them in t04 violates scope boundary per dispatch instructions: "다른 할일의 범위를 침범하면 해당 할일의 담금질이 무의미해진다." The partials are HTMX endpoints already behind `@login_required`, and full protection comes in t05.
