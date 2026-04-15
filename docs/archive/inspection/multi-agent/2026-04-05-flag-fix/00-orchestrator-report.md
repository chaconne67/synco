# Orchestrator Report: Integrity Flag Auto-Correction & Sanitization

**Date:** 2026-04-05
**Verdict:** PASS — all 4 pass criteria met, 336 tests pass

## Problem

Gemini AI가 생성한 integrity_flag가 채용 담당자에게 개발자 용어(`is_current`, `true` 등)를
그대로 노출하고, 자동 교정 가능한 데이터 모순을 RED(중요)로 표시하는 문제.

## Pass Criteria & Results

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `end_date` + `is_current=true` → 자동 `is_current=false` 교정 | PASS |
| 2 | AI flag detail에 개발자 용어 미노출 (한국어 치환) | PASS |
| 3 | 자동 교정 항목은 RED로 표시하지 않음 | PASS |
| 4 | 기존 테스트 전체 통과 + 신규 테스트 추가 | PASS (336/336) |

## Architecture: 3-Layer Defense

수정은 3개 레이어로 구성되어, 어느 한 레이어가 실패해도 사용자에게
개발자 용어가 노출되지 않는 방어 구조를 형성합니다.

```
Layer 1: Prompt (예방)
  prompts.py — Gemini에게 "end_date 있으면 is_current=false로 교정하라"
             + "detail에 개발자 용어 쓰지 마라" 지시

Layer 2: Auto-correction (교정)
  integrity.py — Step 2 이후, end_date가 있는 is_current=true를 강제 교정
               + 관련 AI flag 제거

Layer 3: Sanitization (안전망)
  save.py — DB 저장 직전, 남은 flag detail의 개발자 용어를 한국어로 치환
```

## Changes by Agent

### be-fix (Backend Code)

| File | Change |
|------|--------|
| `integrity.py:901-912` | Auto-correction loop + flag filtering |
| `integrity.py:775-799` | `_is_current_end_date_flag()` helper |
| `save.py:258-286` | `_sanitize_flag_detail()` regex replacements |
| `save.py:297` | Sanitizer integration into `_convert_flags_to_alerts()` |
| `tests/test_de_extraction.py` | 3 new auto-correction tests |
| `tests/test_de_save.py` | 7 new sanitization tests |

### prompt-inspector (Prompt)

| File | Change |
|------|--------|
| `prompts.py:222-230` | end_date/is_current bidirectional rule |
| `prompts.py:249-268` | Flag detail Korean-only rule + severity criteria |
| `prompts.py:368+` | Education prompt: same flag/severity rules |

## Cross-Issue Analysis

두 에이전트의 수정이 교차하는 지점을 검증:

1. **프롬프트(Layer 1)가 "flag 대상이 아닙니다"로 지시 + 코드(Layer 2)가 남은 flag 제거**
   → 이중 방어. Gemini가 지시를 무시해도 코드가 잡아냄. 정합.

2. **프롬프트가 "개발자 용어 금지" + save.py가 regex 치환**
   → 이중 방어. Gemini가 여전히 `is_current`를 쓰면 sanitizer가 "현재 재직 여부"로 치환. 정합.

3. **severity 기준: 프롬프트 "자동 교정 가능한 건 flag 대상 아님" + 코드가 관련 flag 제거**
   → 설령 Gemini가 RED flag을 생성해도 코드가 필터링. 정합.

**교차 충돌 없음.** 세 레이어가 독립적으로 동작하면서 서로 보완.
