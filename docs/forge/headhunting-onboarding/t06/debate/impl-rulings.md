# 구현담금질 쟁점 판정 결과 — t06

**Status:** COMPLETE
**Rounds:** 1
**Models:** codex-cli, gemini-api

---

## Accepted Items

### I-R1-01 [CRITICAL] — Failing test won't fail (scope=mine already filters)
**Sources:** Codex, Gemini (cross-validated)
**Ruling:** ACCEPTED — Test must use `scope=all` and verify `created_by` alone doesn't grant consultant visibility.

### I-R1-02 [CRITICAL] — Variable name mismatch (`qs` vs `projects`)
**Source:** Codex
**Ruling:** ACCEPTED — Use `projects` variable name consistently with existing code.

### I-R1-03 [CRITICAL] — `--timeout=30` not available
**Source:** Codex
**Ruling:** ACCEPTED — Change to `uv run pytest -v`.

### I-R1-04 [MAJOR] — Owner test insufficient
**Sources:** Codex, Gemini (cross-validated)
**Ruling:** ACCEPTED — Add project by another user, test with `scope=all`.

### I-R1-05 [MAJOR] — Missing viewer role test
**Sources:** Codex, Gemini (cross-validated)
**Ruling:** ACCEPTED — Use `pytest.mark.parametrize` for consultant and viewer.

## Rebutted Items

### I-R1-06 [MINOR] — Missing imports in test snippet
**Source:** Gemini
**Ruling:** REBUTTED — test_rbac.py already has base imports; only Client/Project/ProjectStatus are new and shown in snippet.
