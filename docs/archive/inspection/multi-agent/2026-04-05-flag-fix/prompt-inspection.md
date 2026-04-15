# Prompt Inspection Report: integrity_flag Quality

**Date:** 2026-04-05
**Target:** `data_extraction/services/extraction/prompts.py`
**Inspector:** Prompt Inspection Agent
**Framework:** Prompt Golden Rules (no hardcoding, sufficient context, optimized examples)

---

## Pass 1: Original Issue Criteria

### 1. end_date / is_current Logical Consistency — FIXED

**Problem:** `CAREER_SYSTEM_PROMPT` only stated one direction:
> "현재 재직 중이면 end_date는 null, is_current�� true."

Missing inverse: "end_date가 있으면 is_current=false". This allowed contradictory records.

**Fix:** Added principle-based rule explaining WHY the two fields must agree (they represent a single fact — employment status — and contradiction breaks downstream period calculation and overlap detection). The AI corrects contradictions using end_date presence as the source of truth, recording the correction in date_evidence.

### 2. Flag detail Text Quality — FIXED

**Problem:** No formatting guidelines for flag detail text. Developer terms (`is_current=true`, `end_date`, `null`) leaked into recruiter-facing UI.

**Fix:** Added "integrity_flags 작성 규칙" with a litmus test ("비개발자 동료에게 보여줬을 때 바로 이해하는가?") and boundary examples showing O/X pairs with real domain context (company names, dates).

### 3. Severity Criteria — FIXED

**Problem:** RED/YELLOW explained conceptually but no actionable judgment criteria. Auto-correctable contradictions could trigger RED.

**Fix:** Added principle-based severity guidance: "실수로 설명 가능한가, 의도가 의심되는가" as the core question, with WHY for the auto-correct-don't-flag rule (false alarms erode recruiter trust, drowning real fraud signals).

### 4. Schema / Code Alignment — FIXED (minor)

**Problem:** `CAREER_OUTPUT_SCHEMA` hardcoded flag type as `"string (DATE_CONFLICT)"`, suggesting only one type is valid. The AI might avoid generating `DURATION_MISMATCH` or other appropriate types.

**Fix:** Changed to `"string (불일치 유형을 나타내는 식별자, 예: DATE_CONFLICT, DURATION_MISMATCH)"`. Downstream code (`_convert_flags_to_alerts()`) is already type-agnostic.

---

## Pass 2: Golden Rules Deep Inspection

### Rule 1: No Hardcoding

| Location | Issue | Fix |
|----------|-------|-----|
| CAREER severity (Pass 1 draft) | "1년 이상 차이" — hardcoded threshold. AI would skip 11-month discrepancy. | Removed fixed threshold. Replaced with principle: "실수로 설명 가능한가, 의도가 의심되는가" |
| CAREER end_date/is_current (Pass 1 draft) | 4-bullet truth table — enumeration of cases. AI treats as lookup table, not understanding. | Replaced with single principle: "end_date 유무가 재직 여부를 결정, is_current를 일치시켜라" + WHY (후속 시스템 오작동) |
| CAREER_OUTPUT_SCHEMA flag type | `"string (DATE_CONFLICT)"` — single hardcoded type | Opened to descriptive identifier with examples |
| EDUCATION severity (Pass 1 draft) | "학위 과정에 비해 재학 기간이 현저히 짧음" — no reference for "현저히" | Added domain context (학사 4년, 석사 2년, 박사 3~5년) and principle ("정상 범위의 절반 이하이고 정당 사유 미언급") so AI can judge edge cases |

### Rule 2: Sufficient Context (WHY)

| Location | Issue | Fix |
|----------|-------|-----|
| CAREER auto-correct guidance (Pass 1 draft) | "교정만 하고 flag를 생성하지 마세요" — no WHY | Added: "거짓 경보는 담당자의 시스템 신뢰를 떨어뜨립니다. 교정 가능한 형식 불일치까지 보고하면 정작 위조 신호가 묻힙니다." |
| CAREER end_date/is_current (Pass 1 draft) | Rules stated but not explained | Added: "두 필드가 모순되면 후속 시스템(기간 계산, 중복 탐지)이 오작동합니다" — explains the consequence |
| EDUCATION SHORT_DEGREE | "수업연한보다 현저히 짧은 기간" — no reference durations | Added reference durations (학사 4년, 석사 2년, 박사 3~5년) and caveats (학점은행제, 야간, 계절학기) |

### Rule 3: Optimized Examples

| Location | Issue | Fix |
|----------|-------|-----|
| CAREER flag detail (Pass 1 draft) | Examples only showed language style boundary (dev terms X vs Korean O). Did not show the harder judgment: flag-worthy vs. correct-and-move-on. | Added domain-rich examples that include company names, specific dates, and section references — showing what a real flag detail should look like |
| EDUCATION flag detail | No examples at all | Added O/X pair with concrete education scenario |

### Items Confirmed OK (no violation found)

- **STEP1_SYSTEM_PROMPT**: Well-structured with clear WHY for each principle (e.g., "누락 비용 > 노이즈 비용" explains the extraction philosophy). Input characteristics section provides good context. The `skills vs core_competencies` distinction uses a principle ("검색했을 때 해당 기술을 가진 사람만 나와야 하면") rather than enumeration.
- **CAREER field preservation principle**: Correctly gives WHY ("정규화 대상이 아닙니다") and delegates carry-forward to code (`_carry_forward_career_fields` in integrity.py), avoiding information loss.
- **Overall pipeline structure**: Step 1 (faithful extraction, no judgment) → Step 2 (normalize + detect, parallel) → Step 3 (code-based cross-analysis) is clean separation. No "information loss then recovery" anti-pattern.

---

## Changes Made

**File:** `data_extraction/services/extraction/prompts.py`

### CAREER_SYSTEM_PROMPT
1. Replaced 4-rule truth table for end_date/is_current with single principle + WHY
2. Replaced hardcoded severity thresholds with judgment principle ("실수 vs 의도")
3. Added WHY for auto-correct-don't-flag rule (false alarm cost)
4. Replaced language-only flag examples with domain-rich boundary examples

### CAREER_OUTPUT_SCHEMA
5. Opened flag type from hardcoded `DATE_CONFLICT` to descriptive identifier

### EDUCATION_SYSTEM_PROMPT
6. Added reference durations for SHORT_DEGREE judgment (학사 4년, 석사 2년, 박사 3~5년)
7. Added caveat for legitimate degree acceleration (학점은행제, 야간, 계절학기)
8. Added O/X boundary example for flag detail text
9. Added principle-based severity ("정당 사유로 설명 가능한가")

## Test Verification

```
uv run pytest tests/test_de_extraction.py -v
105 passed in 0.97s
```

All tests pass including 3 pre-existing auto-correct behavior tests.
