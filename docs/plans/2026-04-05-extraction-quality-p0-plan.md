# 데이터 추출 품질 P0 개선 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** data_extraction 앱의 출력 안정성과 입력 품질을 높인다. Structured Output 도입, 텍스트 품질 게이트, Critical Field Gate 3개를 순서대로 구현.

**전제:**
- `data_extraction`이 주 경로. `candidates/services/` 구 경로는 동결 (Task 11까지 유지보수 최소화)
- 개발 DB 초기화 완료 상태
- Gemini 3.1 Flash Lite (`gemini-3.1-flash-lite-preview`)

**Tech Stack:** Django 5.2, google-genai SDK, Python 3.13+

---

## 현재 JSON 파싱 방식 (4곳 동일 패턴)

```python
# gemini.py:71-77, integrity.py:68-73, ingest.py:204-210
text = response.text.strip()
if "```" in text:
    text = text.split("```")[1]
    if text.startswith("json"):
        text = text[4:]
data = json.loads(text)
```

문제: LLM이 코드 블록을 안 쓰거나, 여러 개 쓰거나, 깨진 JSON을 반환하면 실패.

---

## Task 1: Gemini Structured Output 도입

**목표:** `response_mime_type="application/json"` + JSON 스키마 강제로 파싱 실패 제거.

**수정 파일:**
- `data_extraction/services/extraction/gemini.py` (lines 58-77)
- `data_extraction/services/extraction/integrity.py` (lines 58-73, _call_gemini)
- `data_extraction/services/batch/request_builder.py` (lines 19-36)
- `data_extraction/services/batch/ingest.py` (lines 200-215, _load_extracted_json)

### Step 1: gemini.py 수정

**현재 (line 58-66):**
```python
config = GenerateContentConfig(
    system_instruction=GEMINI_SYSTEM_PROMPT,
    max_output_tokens=4000,
    temperature=0.3,
)
```

**변경:**
```python
config = GenerateContentConfig(
    system_instruction=GEMINI_SYSTEM_PROMPT,
    max_output_tokens=4000,
    temperature=0.3,
    response_mime_type="application/json",
)
```

**파싱 로직 변경 (lines 71-77):**

현재의 fenced code block 파싱을 제거하고 직접 `json.loads(response.text)`:
```python
# 변경 전
text = response.text.strip()
if "```" in text:
    text = text.split("```")[1]
    if text.startswith("json"):
        text = text[4:]
data = json.loads(text.strip())

# 변경 후
data = json.loads(response.text)
```

- [ ] `gemini.py` config에 `response_mime_type="application/json"` 추가
- [ ] `gemini.py` fenced code block 파싱 로직 제거, `json.loads(response.text)` 직접 사용
- [ ] 1건 수동 추출로 JSON 응답 확인

### Step 2: integrity.py _call_gemini 수정

동일 패턴 적용. `_call_gemini()` (line 58-73):

- [ ] config에 `response_mime_type="application/json"` 추가
- [ ] fenced code block 파싱 제거
- [ ] integrity 파이프라인 1건 테스트

### Step 3: batch request_builder.py 수정

**현재 (lines 31-34):**
```python
"generation_config": {
    "temperature": 0.3,
    "max_output_tokens": 4000,
}
```

**변경:**
```python
"generation_config": {
    "temperature": 0.3,
    "max_output_tokens": 4000,
    "response_mime_type": "application/json",
}
```

- [ ] `request_builder.py`의 `generation_config`에 `response_mime_type` 추가

### Step 4: batch ingest.py 수정

`_load_extracted_json()` (lines 200-215):

- [ ] fenced code block 파싱 로직 제거
- [ ] `json.loads(text)` 직접 사용
- [ ] 단, 하위 호환을 위해 fenced block이 있으면 제거하는 fallback은 유지:
```python
def _load_extracted_json(text: str) -> dict | None:
    raw = text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: structured output 이전 응답 형식 호환
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            try:
                data = json.loads(raw.strip())
            except json.JSONDecodeError:
                return None
        else:
            return None
    return data if isinstance(data, dict) else None
```

### Step 5: 테스트 + 커밋

- [ ] `uv run pytest tests/test_de_*.py -v` — 기존 테스트 통과
- [ ] 실제 10건 추출 (`extract --drive URL --folder Engineer --limit 2 --integrity --workers 5`)
- [ ] JSON 파싱 실패 0건 확인
- [ ] 커밋: `feat(data_extraction): adopt Gemini structured output, remove fenced block parsing`

---

## Task 2: 텍스트 품질 게이트

**목표:** 짧거나 깨진 텍스트가 LLM에 들어가기 전에 차단.

**수정 파일:**
- `data_extraction/services/text.py` (line 197-200, _has_substantive_text 확장)
- `data_extraction/services/pipeline.py` (line 46-49, 분기 전)
- `data_extraction/management/commands/extract.py` (_process_group_inner)

### Step 1: text.py에 품질 분류 함수 추가

`_has_substantive_text()` (line 197) 옆에 새 함수:

```python
def classify_text_quality(text: str) -> str:
    """Classify extracted text quality.

    Returns: 'ok', 'too_short', 'garbled', 'empty'
    """
    if not text or not text.strip():
        return "empty"

    stripped = text.strip()

    # 한글/영문/숫자 비율 체크
    alnum_chars = sum(1 for c in stripped if c.isalnum() or '\uac00' <= c <= '\ud7a3')
    if len(stripped) > 0 and alnum_chars / len(stripped) < 0.3:
        return "garbled"

    # 최소 길이 (이력서는 보통 500자 이상)
    if len(stripped) < 100:
        return "too_short"

    return "ok"
```

- [ ] `text.py`에 `classify_text_quality()` 함수 추가

### Step 2: pipeline.py에서 게이트 적용

`run_extraction_with_retry()` (line 46) 분기 전에:

```python
from data_extraction.services.text import classify_text_quality

quality = classify_text_quality(raw_text)
if quality != "ok":
    return {
        "extracted": None,
        "diagnosis": {
            "verdict": "fail",
            "issues": [{"field": "raw_text", "severity": "error",
                        "message": f"Text quality: {quality}"}],
            "field_scores": {},
            "overall_score": 0.0,
        },
        "attempts": 0,
        "retry_action": "none",
        "raw_text_used": raw_text,
        "integrity_flags": [],
    }
```

- [ ] `pipeline.py`에 텍스트 품질 게이트 추가 (LLM 호출 전)

### Step 3: extract.py에서 게이트 적용

`_process_group_inner()`에서 `preprocess_resume_text()` 후, `run_extraction_with_retry()` 호출 전에 품질 체크. 이미 빈 텍스트 체크는 있으니 (`if not raw_text or not raw_text.strip()`), `classify_text_quality`를 사용하도록 확장:

```python
from data_extraction.services.text import classify_text_quality

quality = classify_text_quality(raw_text)
if quality != "ok":
    self._save_failed_resume(primary, folder_name, f"Text quality: {quality}")
    return False
```

- [ ] `extract.py`의 `_process_group_inner()`에 품질 게이트 적용

### Step 4: 테스트 + 커밋

- [ ] `test_de_text.py`에 `classify_text_quality` 테스트 추가:
  - 빈 문자열 → "empty"
  - "\ufeff\n\n" → "garbled"
  - "짧음" → "too_short"
  - 정상 이력서 텍스트 → "ok"
- [ ] `uv run pytest tests/test_de_*.py -v`
- [ ] 커밋: `feat(data_extraction): add text quality gate before LLM extraction`

---

## Task 3: Critical Field Gate

**목표:** 핵심 필드 하나가 누락/이상이면 카테고리 평균 점수와 무관하게 자동 통과를 차단.

**수정 파일:**
- `data_extraction/services/validation.py` (line 259-286, compute_overall_confidence)
- `data_extraction/services/pipeline.py` (integrity 경로 verdict)
- `data_extraction/services/batch/ingest.py` (line 132-139, verdict 계산)

### Step 1: validation.py에 critical gate 추가

`compute_overall_confidence()` (line 259)에 카테고리 평균 계산 후, critical field check 추가:

```python
def compute_overall_confidence(
    category_scores: dict,
    issues: list[dict],
    field_scores: dict | None = None,
) -> tuple[float, str]:
    values = list(category_scores.values())
    base = sum(values) / len(values) if values else 0.0

    score = base
    for issue in issues:
        if issue.get("severity") == "error":
            score -= 0.05
        elif issue.get("severity") == "warning":
            score -= 0.02

    score = max(0.0, min(1.0, round(score, 3)))

    # Critical field gates (평균 점수와 별도)
    if field_scores:
        # 이름 없으면 무조건 failed
        if field_scores.get("name", 0) == 0.0:
            return score, "failed"
        # 이메일/전화 둘 다 없으면 auto_confirmed 금지
        if field_scores.get("email", 0) == 0.0 and field_scores.get("phone", 0) == 0.0:
            if score >= 0.85:
                return score, "needs_review"

    if score >= 0.85:
        status = "auto_confirmed"
    elif score >= 0.6:
        status = "needs_review"
    else:
        status = "failed"

    return score, status
```

- [ ] `compute_overall_confidence()`에 `field_scores` 파라미터 추가
- [ ] 이름 없으면 무조건 `failed`
- [ ] 이메일+전화 둘 다 없으면 `auto_confirmed` 차단 → `needs_review`

### Step 2: 호출부 수정

`compute_overall_confidence()` 시그니처가 바뀌니 호출부 수정:

**validation.py `validate_extraction()` (line 283):**
```python
score, status = compute_overall_confidence(category_scores, all_issues, field_scores)
```

**pipeline.py (legacy, line 129):**
- `validate_extraction()` 결과를 그대로 쓰므로 자동 적용됨

**pipeline.py (integrity, line 88):**
- `_build_integrity_diagnosis()`가 별도 경로이므로, 이 경로도 field_scores를 넘겨야 함:
```python
diagnosis = _build_integrity_diagnosis(flags, field_scores)
# diagnosis에 validation_status를 critical gate 적용 버전으로 덮어쓰기
from data_extraction.services.validation import compute_overall_confidence
_, gated_status = compute_overall_confidence(category_scores, [], field_scores)
```

**batch/ingest.py (line 132-139):**
- `validate_extraction()` 결과를 그대로 쓰므로 자동 적용됨

- [ ] `validate_extraction()` 내부에서 `field_scores` 전달 수정
- [ ] `pipeline.py` integrity 경로에서 critical gate 적용
- [ ] `batch/ingest.py`는 `validate_extraction()` 사용하므로 자동 적용 확인

### Step 3: views.py 실시간 계산 수정

`candidates/views.py`에서 `compute_overall_confidence()` 호출부:

```python
live_score, _ = compute_overall_confidence(category_scores, [], field_scores)
```

- [ ] `views.py`의 `compute_overall_confidence()` 호출에 `field_scores` 전달

### Step 4: data_extraction/services/validation.py 동기화

`data_extraction/services/validation.py`에 동일 변경 적용 (주 경로).

- [ ] `data_extraction/services/validation.py`에도 동일 critical gate 적용

### Step 5: 테스트 + 커밋

- [ ] `test_de_validation.py`에 critical gate 테스트 추가:
  - 이름 없으면 → failed (점수 높아도)
  - 이메일+전화 없으면 → auto_confirmed 불가
  - 이메일 있으면 → 정상 auto_confirmed 가능
- [ ] `candidates/services/validation.py`에도 동일 변경 (구 경로 최소 동기화)
- [ ] `uv run pytest -v` 전체 통과
- [ ] 커밋: `feat(data_extraction): add critical field gates to validation`

---

## Task 4: 구 경로 동결 선언

- [ ] `CLAUDE.md`에 추가:
```markdown
## 추출 경로 정책

- **주 경로:** `data_extraction/` 앱. 모든 신규 개선은 이 경로에만 적용.
- **구 경로:** `candidates/services/` 추출 관련 파일 (retry_pipeline, gemini_extraction, integrity/, validation 등). Task 11 정리 전까지 동결. 버그 수정 외 변경 금지.
- **CLI:** `extract` 커맨드 사용. `import_resumes`는 동결.
```

- [ ] 커밋: `docs: declare data_extraction as primary extraction path, freeze legacy`

---

## Task 5: 통합 테스트

- [ ] 전체 재추출 20건 (폴더별 1개): `extract --drive URL --limit 1 --integrity --workers 10`
- [ ] JSON 파싱 실패 0건 확인
- [ ] 텍스트 품질 게이트 동작 확인 (짧은 텍스트 차단)
- [ ] Critical field gate 동작 확인 (이름 없는 후보자 → failed)
- [ ] `uv run pytest -v` 전체 통과
- [ ] 커밋

---

## 완료 기준

1. Gemini 응답이 `application/json`으로 직접 반환됨 (fenced block 파싱 불필요)
2. 100자 미만 또는 깨진 텍스트는 LLM 호출 없이 즉시 실패 처리
3. 이름 없으면 점수와 무관하게 `failed`
4. 이메일+전화 둘 다 없으면 `auto_confirmed` 불가
5. CLAUDE.md에 주 경로/구 경로 정책 명시
6. 전체 테스트 통과
