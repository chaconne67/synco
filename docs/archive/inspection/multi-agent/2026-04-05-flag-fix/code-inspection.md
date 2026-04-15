# Code Inspection Report: Auto-correction & Flag Sanitization

**Date:** 2026-04-05
**Agent:** Backend

## Changes Made

### Layer 1: Auto-correction (`data_extraction/services/extraction/integrity.py`)

**Location:** `run_integrity_pipeline()`, after career ordering (line ~865), before Step 3 cross-analysis.

**What:**
- Added auto-correction loop: if a career has both `end_date` and `is_current=True`, set `is_current=False`.
- Added `_is_current_end_date_flag()` helper to identify AI-generated flags about this specific contradiction.
- After auto-correction, filters out those flags from `all_flags` since the issue has been resolved programmatically.

**Why:** The AI was generating YELLOW flags for `is_current`/`end_date` contradictions, surfacing them to recruiters as "important" alerts. This is a deterministic contradiction that the system can resolve without human intervention.

### Layer 2: Flag detail sanitization (`data_extraction/services/save.py`)

**Location:** New `_sanitize_flag_detail()` function, called from `_convert_flags_to_alerts()`.

**What:** Regex-based replacement of developer terms in AI-generated flag detail text:
- `is_current` -> "현재 재직 여부"
- `end_date` -> "종료일", `start_date` -> "시작일"
- `true`/`True` -> "예", `false`/`False` -> "아니오"
- `null`/`None` -> "미입력"
- `boolean` -> "참/거짓 값"

**Why:** AI-generated flag details sometimes contain developer-facing terms that are meaningless to recruiters. This acts as a safety net to sanitize any remaining developer terms that slip through the AI's output.

**Regex note:** Standard `\b` word boundaries don't work between ASCII and Korean characters. Used negative lookahead/lookbehind for ASCII word characters (`[a-zA-Z_]`) instead.

### Tests Added

**`tests/test_de_extraction.py`** — `TestAutoCorrectIsCurrentEndDate` (3 tests):
- `test_is_current_corrected_when_end_date_present`: Career with end_date + is_current=True gets corrected, related flag removed.
- `test_no_correction_when_no_end_date`: Career with is_current=True but no end_date stays unchanged.
- `test_unrelated_flags_preserved`: Only is_current contradiction flags are removed; other flags survive.

**`tests/test_de_save.py`** — `TestSanitizeFlagDetail` (7 tests):
- Individual term replacements: is_current, true, false, null, boolean
- Clean text passthrough
- Integration: `_convert_flags_to_alerts()` applies sanitizer

## Test Results

All 336 tests pass (`uv run pytest -v`).

## Files Modified

| File | Change |
|------|--------|
| `data_extraction/services/extraction/integrity.py` | Auto-correction logic + `_is_current_end_date_flag()` helper |
| `data_extraction/services/save.py` | `_sanitize_flag_detail()` + integrated into `_convert_flags_to_alerts()` |
| `tests/test_de_extraction.py` | 3 new tests for auto-correction |
| `tests/test_de_save.py` | 7 new tests for sanitization |
