# 데이터 추출 파이프라인 구현 계획서

**작성일:** 2026-04-05
**갱신일:** 2026-04-05
**근거 문서:** [../inspection/extraction_pipeline_audit.md](../inspection/extraction_pipeline_audit.md)

---

## 실행 순서

| 단계 | 작업 | 성격 |
|------|------|------|
| 1 | 스키마 단일화 | 리팩토링 (기능 변경 없음) |
| 2 | Step 1 스키마 보강 | 추출 개선 |
| 3 | Step 2 스키마 보강 + carry-forward | 정규화 개선 |
| 4 | `_etc.type` 정규화 + 뷰 소비 경로 수정 | 표시 개선 |
| 5 | 기존 데이터 보정 | 마이그레이션 |
| 6 | 검증 | QA |

---

## 1단계: 스키마 단일화

### 목표

동일 개념의 스키마가 4곳에 중복 정의되어 있으므로, 한 곳에서 정의하고 나머지는 import한다.

### 현재 중복 현황

| 스키마 | 원본 위치 | 복제 위치 |
|--------|----------|----------|
| `STEP1_SYSTEM_PROMPT` | `candidates/.../step1_extract.py:15` | `data_extraction/.../prompts.py:171` |
| `STEP1_SCHEMA` | `candidates/.../step1_extract.py:118` | `data_extraction/.../prompts.py:274` |
| `CAREER_SYSTEM_PROMPT` | `candidates/.../step2_normalize.py:12` | `data_extraction/.../prompts.py:348` |
| `CAREER_OUTPUT_SCHEMA` | `candidates/.../step2_normalize.py:66` | `data_extraction/.../prompts.py:402` |
| `EDUCATION_SYSTEM_PROMPT` | `candidates/.../step2_normalize.py:94` | `data_extraction/.../prompts.py:434` |
| `EDUCATION_OUTPUT_SCHEMA` | `candidates/.../step2_normalize.py:135` | `data_extraction/.../prompts.py:475` |
| `EXTRACTION_SYSTEM_PROMPT` | `candidates/.../llm_extraction.py:13` | `data_extraction/.../prompts.py:13` |
| `EXTRACTION_JSON_SCHEMA` | `candidates/.../llm_extraction.py:68` | `data_extraction/.../prompts.py:68` |

### 설계

**단일 소스:** `candidates/services/integrity/` 디렉토리의 원본 파일을 정본(canonical source)으로 한다.

- `step1_extract.py` → `STEP1_SYSTEM_PROMPT`, `STEP1_SCHEMA`
- `step2_normalize.py` → `CAREER_*`, `EDUCATION_*`
- `llm_extraction.py` → `EXTRACTION_SYSTEM_PROMPT`, `EXTRACTION_JSON_SCHEMA` (레거시)

**수정 대상:**

1. `data_extraction/services/extraction/prompts.py`
   - Step 1 / Career / Education 상수 정의 삭제
   - `candidates` 쪽에서 import
   - `build_step1_prompt()`, `build_extraction_prompt()` 함수는 유지 (프롬프트 조립 로직)

2. `data_extraction/services/extraction/integrity.py`
   - import 경로를 `data_extraction.services.extraction.prompts` → `candidates.services.integrity.*`로 변경

3. `batch_extract/services/request_builder.py`
   - `candidates.services.llm_extraction`에서 직접 import 유지 (이미 그렇게 되어 있음)
   - `candidates.services.gemini_extraction`에서 `GEMINI_SYSTEM_PROMPT` import도 확인

### 작업 목록

```
[ ] prompts.py에서 STEP1_*, CAREER_*, EDUCATION_* 상수 정의 삭제, import로 교체
[ ] prompts.py에서 build_step1_prompt() 함수는 유지 (import된 STEP1_SCHEMA 사용하도록)
[ ] integrity.py import 경로 수정
[ ] 기존 테스트가 있으면 실행하여 regression 확인
[ ] grep으로 모든 import 경로 확인: STEP1_SCHEMA, CAREER_OUTPUT_SCHEMA 등
```

### 완료 기준

- `grep -r "STEP1_SCHEMA\|STEP1_SYSTEM_PROMPT" --include="*.py"` 결과에서 정의(=)가 `step1_extract.py`에만 존재
- `grep -r "CAREER_OUTPUT_SCHEMA\|CAREER_SYSTEM_PROMPT" --include="*.py"` 결과에서 정의가 `step2_normalize.py`에만 존재
- `uv run pytest -v` 통과

---

## 2단계: Step 1 스키마 보강

### 목표

원문에 명시될 수 있는 데이터인데 Step 1 스키마에 없어서 `_etc`로 밀리는 필드를 추가한다.

### 추가할 필드

#### careers[] 추가 필드

| 필드 | 타입 | 추출 지침 (프롬프트에 추가) |
|------|------|--------------------------|
| `reason_left` | `string \| null` | 퇴사 사유. 입사/퇴사 사유가 별도 섹션에 있으면 해당 회사의 career 항목에 넣으세요. career_etc에 넣지 마세요. |
| `achievements` | `string \| null` | 주요 성과, 실적. 별도 "성과" 섹션의 내용도 해당 회사 항목에 넣으세요. |
| `salary` | `integer \| null` | 해당 직장의 연봉 (만원 단위). 없으면 null. |
| `company_en` | `string \| null` | 영문 회사명. 한글/영문이 병기되어 있으면 company에 한글, company_en에 영문. |

#### educations[] 추가 필드

| 필드 | 타입 | 추출 지침 |
|------|------|----------|
| `gpa` | `string \| null` | 학점. 원문 그대로 (예: "3.8/4.5", "4.0"). |

#### language_skills[] 추가 필드

| 필드 | 타입 | 추출 지침 |
|------|------|----------|
| `level` | `string \| null` | 어학 수준 (예: "상", "비즈니스", "Native"). 시험 점수와 별개로 수준이 기재되어 있을 때. |

### Step 1 프롬프트 보강

`STEP1_SYSTEM_PROMPT`에 다음 원칙 추가:

```
### 입사/퇴사 사유, 성과의 배치 원칙

이력서에 입사 사유, 퇴사 사유, 성과가 별도 섹션이나 표로 기재된 경우가 많습니다.
이 정보는 career_etc에 넣지 말고, 해당 회사의 careers[] 항목에 넣으세요.

- 퇴사 사유 → 해당 회사의 reason_left
- 성과/실적 → 해당 회사의 achievements
- 연봉 → 해당 회사의 salary (만원 단위 정수)

회사 매칭은 회사명과 기간을 기준으로 하세요.
매칭이 불확실하면 career_etc에 넣으세요. 잘못된 회사에 붙이는 것보다 career_etc에 남기는 것이 안전합니다.
```

### STEP1_SCHEMA 변경

```diff
  "careers": [
    {
      "company": "string (원문 그대로)",
+     "company_en": "string | null (영문 회사명)",
      "position": "string | null",
      "department": "string | null",
      "start_date": "string | null (원문 그대로)",
      "end_date": "string | null (원문 그대로)",
      "duration_text": "string | null (괄호 안 기간 표기 원문 그대로)",
      "is_current": "boolean",
      "duties": "string | null",
+     "achievements": "string | null (주요 성과/실적)",
+     "reason_left": "string | null (퇴사 사유)",
+     "salary": "integer | null (만원 단위)",
      "source_section": "string (출처 섹션)"
    }
  ],
  "educations": [
    {
      "institution": "string (원문 그대로)",
      "degree": "string | null",
      "major": "string | null",
+     "gpa": "string | null (원문 그대로)",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean",
      "status": "string | null (졸업/중퇴/수료 등 원문 그대로)",
      "source_section": "string (출처 섹션)"
    }
  ],
  ...
  "language_skills": [
-   {"language": "string", "test_name": "string | null", "score": "string | null"}
+   {"language": "string", "test_name": "string | null", "score": "string | null", "level": "string | null"}
  ],
```

### 수정 파일

```
[ ] candidates/services/integrity/step1_extract.py — STEP1_SYSTEM_PROMPT, STEP1_SCHEMA
```

### 완료 기준

- 신지원 이력서로 재추출했을 때 `reason_left`에 퇴사 사유가 들어가고, `career_etc`에 중복 항목이 생기지 않음
- 학점이 있는 이력서에서 `educations[].gpa`가 채워짐
- `uv run pytest -v` 통과

---

## 3단계: Step 2 스키마 보강 + carry-forward

### 목표

Step 2 정규화 출력이 Step 1에서 추출한 필드를 탈락시키지 않도록 보강한다.

### 설계 원칙

Step 2 정규화는 LLM 호출이다. LLM이 필드를 빠뜨릴 수 있으므로:

1. Step 2 출력 스키마에 필드 추가 (LLM에게 알려줌)
2. pipeline.py에서 carry-forward 로직 추가 (LLM이 빠뜨려도 Step 1 값을 복원)

### 3-A: CAREER_OUTPUT_SCHEMA 보강

```diff
  "careers": [
    {
      "company": "string",
      "company_en": "string | null",
      "position": "string | null",
      "department": "string | null",
      "start_date": "string (YYYY-MM)",
      "end_date": "string | null (YYYY-MM)",
+     "end_date_inferred": "string | null (YYYY-MM, 추정된 종료일)",
+     "duration_text": "string | null (Step 1 원문 그대로 보존)",
+     "date_evidence": "string | null (날짜 선택 근거)",
+     "date_confidence": "float | null (0.0-1.0)",
      "is_current": "boolean",
      "duties": "string | null",
      "achievements": "string | null",
+     "reason_left": "string | null",
+     "salary": "integer | null (만원 단위)",
      "order": "integer (최신순 0부터)"
    }
  ],
```

`end_date_inferred`, `date_evidence`, `date_confidence`는 Step 2가 생성하는 산물이다.
현재 모델에 필드가 있고(`Career.end_date_inferred`, `Career.date_evidence`, `Career.date_confidence`),
save.py도 이를 매핑하지만, Step 2 출력 스키마에 빠져 있어 LLM이 출력하지 않는다.

### 3-B: CAREER_SYSTEM_PROMPT 보강

```
### 날짜 추정 원칙

여러 섹션의 날짜가 충돌하면, 선택한 값을 start_date/end_date에 넣고:
- 추정한 종료일이 있으면 end_date_inferred에 넣으세요.
- 날짜 선택의 근거를 date_evidence에 짧게 기록하세요.
- 판단의 확신도를 date_confidence에 0.0~1.0으로 넣으세요.

### 필드 보존 원칙

Step 1에서 추출된 reason_left, achievements, salary, duration_text는
정규화 대상이 아닙니다. 같은 회사의 여러 항목을 병합할 때,
이 값들은 가장 상세한 항목의 값을 그대로 가져오세요.
```

### 3-C: EDUCATION_OUTPUT_SCHEMA 보강

```diff
  "educations": [
    {
      "institution": "string",
      "degree": "string | null",
      "major": "string | null",
+     "gpa": "string | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean"
    }
  ],
```

### 3-E: validator 보강 + 단일화

현재 `validate_step2()`는 `company`와 `start_date` 존재, 날짜 포맷, flag reasoning만 검증한다.
추가된 필드가 통째로 빠져도 오류로 잡히지 않는다.

**validator 단일화:** `candidates/services/integrity/validators.py`와 `data_extraction/services/extraction/validators.py`가 동일 내용으로 중복되어 있다. 1단계 스키마 단일화와 마찬가지로 `candidates` 쪽을 정본으로 하고 `data_extraction`은 import로 교체한다.

**Step 2 validator에 추가할 검증:**

```python
# carry-forward 대상 필드가 원본에 있었는데 Step 2에서 전부 사라진 경우 경고
step1_has_reason = any(c.get("reason_left") for c in raw_careers)
step2_has_reason = any(c.get("reason_left") for c in normalized_careers)
if step1_has_reason and not step2_has_reason:
    issues.append({
        "severity": "warning",
        "message": "Step 1 had reason_left data but Step 2 dropped all of it",
    })
```

이 검증은 carry-forward가 있으므로 실패해도 복구 가능하지만, 로깅 목적으로 추적한다.

**입력 계약 변경:** 현재 `validate_step2(normalized: dict)`는 Step 2 출력만 받는다.
Step 1 원본 대비 검증을 위해 시그니처를 확장한다:

```python
def validate_step2(
    normalized: dict,
    *,
    raw_careers: list[dict] | None = None,
) -> list[dict]:
```

`raw_careers`가 주어지면 carry-forward 대상 필드 탈락을 검증한다.
기존 호출부(`pipeline.py` line 79, `data_extraction/.../integrity.py`)도 함께 수정한다.
`raw_careers=None`이면 기존 동작과 동일 (하위 호환).

### 3-F: pipeline.py carry-forward 로직

Step 2 결과에서 필드가 누락된 경우, Step 1 원본에서 복원하는 코드를 추가한다.

#### 매칭 전략: company 단독 매칭 금지

동일 회사 재입사, 같은 회사 내 복수 경력, 계열사/영문 병기 케이스에서
company명만으로 매칭하면 다른 경력에 잘못된 값을 덮어쓸 수 있다.

**복합키 매칭:** `(company_normalized, start_date)` 쌍으로 매칭한다.
- company 정규화: `(주)`, `㈜`, `주식회사` 제거, strip, lower
- start_date가 Step 2에서 YYYY-MM으로 정규화되고 Step 1은 원문이므로,
  Step 1 start_date도 YYYY-MM 패턴으로 변환 후 비교
- 복합키가 일치하는 항목이 없으면 **carry-forward하지 않음** (오매칭보다 누락이 안전)

```python
import re

_COMPANY_NOISE = re.compile(r"\(주\)|㈜|주식회사|\s+")

def _normalize_company(name: str) -> str:
    return _COMPANY_NOISE.sub("", name).strip().lower()

def _normalize_date_to_ym(date_str: str) -> str | None:
    """다양한 날짜 형식을 YYYY-MM으로 변환. 실패 시 None.

    지원 형식:
    - YYYY-MM, YYYY/MM, YYYY.MM (구분자 기반)
    - 2019년 3월, 2019년03월 (한국어 원문)
    - 2019.03 ~ 현재 (범위 표기에서 시작일만 추출)
    """
    if not date_str:
        return None
    # 범위 표기에서 시작일만 사용
    date_str = re.split(r"\s*[~\-–—]\s*", date_str)[0].strip()
    # YYYY-MM, YYYY/MM, YYYY.MM
    m = re.match(r"(\d{4})[-./](\d{1,2})", date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    # 2019년 3월, 2019년03월
    m = re.match(r"(\d{4})년\s*(\d{1,2})월?", date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return None

def _carry_forward_career_fields(
    normalized: list[dict],
    raw_careers: list[dict],
) -> None:
    """Step 2가 빠뜨린 필드를 Step 1 원본에서 복원.

    매칭 기준: (company_normalized, start_date_ym) 복합키.
    복합키 매칭 실패 시 carry-forward하지 않음.
    """
    CARRY_FIELDS = ["reason_left", "achievements", "salary", "duration_text", "company_en"]

    # Step 1 데이터를 복합키로 인덱싱
    raw_index: dict[tuple[str, str], list[dict]] = {}
    for raw in raw_careers:
        company_key = _normalize_company(raw.get("company") or "")
        date_key = _normalize_date_to_ym(raw.get("start_date") or "")
        if company_key and date_key:
            raw_index.setdefault((company_key, date_key), []).append(raw)

    for career in normalized:
        company_key = _normalize_company(career.get("company") or "")
        date_key = career.get("start_date") or ""  # Step 2는 이미 YYYY-MM
        matches = raw_index.get((company_key, date_key), [])
        if not matches:
            continue
        best = max(matches, key=lambda r: sum(1 for f in CARRY_FIELDS if r.get(f)))
        for field in CARRY_FIELDS:
            if not career.get(field) and best.get(field):
                career[field] = best[field]
```

호출 위치: `pipeline.py`의 Step 2 결과 수집 직후 (line 105 부근)

```python
if career_result:
    normalized_careers = career_result.get("careers", [])
    _carry_forward_career_fields(normalized_careers, careers_raw)  # ← 추가
    all_flags.extend(career_result.get("flags", []))
```

Education에도 동일 패턴 적용 (institution + end_year 복합키로 gpa carry-forward).

### 3-G: pipeline.py에서 step1 원본을 결과에 포함

carry-forward와 backfill의 안전성 검증을 위해, 최소한 Step 1 원본을 최종 결과에 동봉한다.
이는 `raw_extracted_json` 전체 구조 변경(P1)과는 별개로, 현재 작업 묶음에서 할 수 있는 최소 보존이다.

```python
# pipeline.py Assemble result 부분
return apply_regex_field_filters({
    ...
    "pipeline_meta": {
        "step1_items": len(careers_raw) + len(educations_raw),
        "retries": retries,
        "step1_careers_raw": careers_raw,      # ← 추가: carry-forward 감사 추적용
        "step1_educations_raw": educations_raw, # ← 추가
    },
})
```

`save.py`에서 `pipeline_meta`는 `raw_extracted_json`에 포함되므로, 별도 DB 변경 없이 Step 1 원본이 보존된다.

**주의: 이것은 임시 보존 전략이다.** 감사 문서의 장기 방향은 `raw_extracted_json`을 `{step1, step2, final}` 구조로 전환하는 것이며, `pipeline_meta` 안에 step1 원본을 끼워 넣는 현재 방식은 그 전환 전의 중간 단계다. 구현 시 이 점을 코드 주석으로 남겨서, 이 구조가 최종안처럼 굳어지지 않도록 한다.

### 수정 파일

```
[ ] candidates/services/integrity/step2_normalize.py — CAREER_OUTPUT_SCHEMA, CAREER_SYSTEM_PROMPT, EDUCATION_OUTPUT_SCHEMA
[ ] candidates/services/integrity/pipeline.py — carry-forward 함수 추가, step1 원본 보존, 호출
[ ] candidates/services/integrity/validators.py — Step 2 validator 시그니처 확장 + carry-forward 필드 경고
[ ] data_extraction/services/extraction/validators.py → candidates 쪽 import로 교체 (1단계 단일화의 연장)
```

### 완료 기준

- Step 2 출력에 `reason_left`, `salary`, `duration_text`, `end_date_inferred`, `date_evidence`, `date_confidence` 포함 확인
- LLM이 빠뜨려도 carry-forward가 복원하는지 확인 (로그 또는 단위 테스트)
- validator가 중복 정의 없이 단일 소스에서 동작
- `uv run pytest -v` 통과

---

## 4단계: `_etc.type` 정규화 + 뷰 소비 경로 수정

### 목표

1. `_etc` 필드의 `type` 값을 canonical type으로 정규화
2. 뷰에서 `_etc`를 type별로 분리하여 전용 UI 블록에 전달
3. 레거시 JSONField 직접 참조 제거

### 4-A: Canonical type 정의

실제 데이터 분포를 기반으로 정의한다.

#### career_etc canonical types

| canonical | alias (실제 출현값) | 매핑 대상 |
|-----------|-------------------|----------|
| `퇴사사유` | `퇴사 사유`, `입사/퇴사 사유`, `입사계기 및 퇴사이유`, `입사 계기 및 퇴사 사유`, `이직 사유`, `전배 사유` | → Step 1 보강 후 여기에 올 일 없음. 이미 있는 데이터 정리용 |
| `수상` | `수상`, `수상 및 기타 경력`, `포상` | `awards_data`로 분리 |
| `특허` | `특허` | `patents_data`로 분리 |
| `교육` | `교육` | `trainings_data`로 분리 |
| `기타` | 위 어디에도 안 맞는 값 | `career_etc` 기타 섹션에 유지 |

#### education_etc canonical types

| canonical | alias | 매핑 대상 |
|-----------|-------|----------|
| `교육` | `교육`, `교육 및 연수`, `교육 수료`, `교육 프로그램`, `교육이수` | `trainings_data`로 분리 |
| `해외연수` | `해외연수`, `어학연수` | `trainings_data`로 분리 (institution에 국가 포함) |
| `수상` | `수상경력`, `수상내역` | `awards_data`로 분리 |
| `기타` | 나머지 | `education_etc` 기타 섹션에 유지 |

#### skills_etc canonical types

| canonical | alias | 매핑 대상 |
|-----------|-------|----------|
| `교육` | `교육`, `교육 이수`, `전문 교육 과정`, `교육 및 훈련` | `trainings_data`로 분리 |
| `수상` | `성과`, `성과 지표` | `awards_data`로 분리 |
| `급여` | `급여조건`, `급여 조건`, `현재 급여 조건`, `희망 급여 조건`, `희망 조건`, `희망조건` | 이미 salary_detail에 있을 수 있음. 중복 체크 후 제거 또는 유지 |
| `기타` | 나머지 | `skills_etc` 기타 섹션에 유지 |

#### personal_etc canonical types

| canonical | alias | 매핑 대상 |
|-----------|-------|----------|
| `병역` | `병역`, `병역사항`, `군 복무` | 이미 `military_service`에 있을 수 있음. 중복 체크 |
| `가족` | `가족관계`, `결혼여부`, `혼인여부` | 이미 `family_info`에 있을 수 있음. 중복 체크 |
| `기타` | 나머지 | `personal_etc` 기타 섹션에 유지 |

### 4-B: 프로젝트 처리 결정

현재 `career_etc`에 `프로젝트`라는 type이 **실제 데이터에 존재하지 않는다.** (조회 결과 0건)
프로젝트 데이터는 이미 경력 섹션의 별도 하위 블록으로 처리되며, `Candidate.projects` JSONField도 전 후보자에서 빈 배열이다.

따라서:
- `projects_data`는 **현재 상태를 유지** (빈 배열이 넘어감)
- 향후 `career_etc`에 프로젝트 type이 실제로 출현하면, alias map에 추가하고 shape 변환기를 만든다
- 완료 기준에서 "프로젝트 전용 UI 블록 표시"는 **제거** — 현재 데이터가 없으므로 검증 불가

### 4-C: shape 변환 — `_etc` dict를 UI 기대 형태로 맞추기

**핵심 문제:** `split_*_etc()`가 버킷팅만 하면 UI가 깨진다.

| 출처 | 원본 shape | 템플릿이 기대하는 shape |
|------|-----------|----------------------|
| `education_etc` | `{type, title, institution, date, description}` | trainings: `{name, institution, date, duration}` |
| `skills_etc` | `{type, title, description, date}` | trainings: `{name, institution, date, duration}` |
| `career_etc` | `{type, name, company, role, ...description}` | awards: `{name, issuer, date, project}` |
| `career_etc` | `{type, name, ...}` | patents: `{title, type, country, date, number}` |

기존 `candidates/services/detail_normalizers.py`에 이미 shape 변환 함수가 있다:
- `normalize_awards()` → `{name, issuer, date, project}` (line 58)
- `normalize_trainings()` → `{name, institution, date, duration}` (line 194)
- `normalize_patents()` → `{title, type, country, date, number}` (line 241)

이 함수들은 다양한 key alias를 처리하므로 (`title`→`name`, `description`→`project` 등) `_etc` dict를 그대로 넣어도 대부분 매핑된다.

**설계:** `split_*_etc()`에서 버킷팅 후, 기존 normalizer를 통과시켜 shape을 맞춘다.

### 4-D: 정규화 함수

위치: `candidates/services/etc_normalizer.py` (신규 파일)

```python
"""_etc.type canonicalization, splitting, and shape normalization."""

from __future__ import annotations

from candidates.services.detail_normalizers import (
    normalize_awards,
    normalize_overseas,
    normalize_patents,
    normalize_projects,
    normalize_trainings,
)

# ── alias → canonical 매핑 ──

_CAREER_ETC_ALIASES: dict[str, str] = {
    "퇴사 사유": "퇴사사유",
    "입사/퇴사 사유": "퇴사사유",
    "입사계기 및 퇴사이유": "퇴사사유",
    "입사 계기 및 퇴사 사유": "퇴사사유",
    "이직 사유": "퇴사사유",
    "전배 사유": "퇴사사유",
    "수상 및 기타 경력": "수상",
    "포상": "수상",
    "수상": "수상",
    "특허": "특허",
    "교육": "교육",
}
# 2차 keyword contains 매칭 — 자유서술 변형 대응
# 순서 중요: 먼저 매칭된 것이 우선
_CAREER_ETC_KEYWORDS: dict[str, str] = {
    "퇴사": "퇴사사유",
    "이직": "퇴사사유",
    "퇴직": "퇴사사유",
    "수상": "수상",
    "포상": "수상",
    "상훈": "수상",
    "특허": "특허",
    "교육": "교육",
    "훈련": "교육",
    "연수": "교육",
    "프로젝트": "프로젝트",
    "해외": "해외경험",
}

_EDUCATION_ETC_ALIASES: dict[str, str] = {
    "교육": "교육",
    "교육 및 연수": "교육",
    "교육 수료": "교육",
    "교육 프로그램": "교육",
    "교육이수": "교육",
    "해외연수": "교육",
    "어학연수": "교육",
    "수상경력": "수상",
    "수상내역": "수상",
}
_EDUCATION_ETC_KEYWORDS: dict[str, str] = {
    "교육": "교육",
    "훈련": "교육",
    "연수": "교육",
    "수상": "수상",
    "상훈": "수상",
}

_SKILLS_ETC_ALIASES: dict[str, str] = {
    "교육": "교육",
    "교육 이수": "교육",
    "전문 교육 과정": "교육",
    "교육 및 훈련": "교육",
    "성과": "수상",
    "성과 지표": "수상",
}
_SKILLS_ETC_KEYWORDS: dict[str, str] = {
    "교육": "교육",
    "훈련": "교육",
    "과정": "교육",
    "수상": "수상",
    "성과": "수상",
}


def _canonicalize(item: dict, aliases: dict[str, str], keywords: dict[str, str]) -> str:
    """Return canonical type for an _etc item.

    1차: exact match (aliases)
    2차: keyword contains match (keywords) — 자유서술 변형 대응
    """
    raw_type = (item.get("type") or "").strip()
    # exact match first
    if raw_type in aliases:
        return aliases[raw_type]
    # keyword contains match
    for keyword, canonical in keywords.items():
        if keyword in raw_type:
            return canonical
    return "기타"


def split_career_etc(items: list[dict]) -> dict:
    """career_etc → {awards, patents, trainings, remaining}

    awards/patents/trainings는 detail_normalizers를 통과해 UI shape으로 변환.
    """
    raw_awards, raw_patents, raw_trainings, raw_projects, raw_overseas, remaining = [], [], [], [], [], []
    for item in items:
        canonical = _canonicalize(item, _CAREER_ETC_ALIASES, _CAREER_ETC_KEYWORDS)
        if canonical == "수상":
            raw_awards.append(item)
        elif canonical == "특허":
            raw_patents.append(item)
        elif canonical == "교육":
            raw_trainings.append(item)
        elif canonical == "프로젝트":
            raw_projects.append(item)
        elif canonical == "해외경험":
            raw_overseas.append(item)
        elif canonical == "퇴사사유":
            pass  # 5단계 backfill 후 Career.reason_left로 이관됨
        else:
            remaining.append(item)
    return {
        "awards": normalize_awards(raw_awards),
        "patents": normalize_patents(raw_patents),
        "trainings": normalize_trainings(raw_trainings),
        "projects": normalize_projects(raw_projects),
        "overseas": normalize_overseas(raw_overseas),
        "remaining": remaining,
    }


def split_education_etc(items: list[dict]) -> dict:
    """education_etc → {trainings, awards, remaining}"""
    raw_trainings, raw_awards, remaining = [], [], []
    for item in items:
        canonical = _canonicalize(item, _EDUCATION_ETC_ALIASES, _EDUCATION_ETC_KEYWORDS)
        if canonical == "교육":
            raw_trainings.append(item)
        elif canonical == "수상":
            raw_awards.append(item)
        else:
            remaining.append(item)
    return {
        "trainings": normalize_trainings(raw_trainings),
        "awards": normalize_awards(raw_awards),
        "remaining": remaining,
    }


def split_skills_etc(items: list[dict]) -> dict:
    """skills_etc → {trainings, awards, remaining}"""
    raw_trainings, raw_awards, remaining = [], [], []
    for item in items:
        canonical = _canonicalize(item, _SKILLS_ETC_ALIASES, _SKILLS_ETC_KEYWORDS)
        if canonical == "교육":
            raw_trainings.append(item)
        elif canonical == "수상":
            raw_awards.append(item)
        else:
            remaining.append(item)
    return {
        "trainings": normalize_trainings(raw_trainings),
        "awards": normalize_awards(raw_awards),
        "remaining": remaining,
    }
```

### 4-E: 뷰 수정

위치: `candidates/views.py` — `candidate_detail` 함수 (line 352), `review_detail` 함수 (line 107)

두 뷰 모두 같은 helper를 쓰도록 통일한다.

```python
from candidates.services.etc_normalizer import (
    split_career_etc,
    split_education_etc,
    split_skills_etc,
)

def _build_etc_context(candidate) -> dict:
    """_etc 필드를 type별로 분리하고 UI shape으로 변환."""
    career_split = split_career_etc(candidate.career_etc or [])
    edu_split = split_education_etc(candidate.education_etc or [])
    skills_split = split_skills_etc(candidate.skills_etc or [])

    return {
        "trainings_data": (
            edu_split["trainings"]
            + skills_split["trainings"]
            + career_split["trainings"]
        ),
        "awards_data": (
            career_split["awards"]
            + edu_split["awards"]
            + skills_split["awards"]
        ),
        "patents_data": career_split["patents"],
        "projects_data": career_split.get("projects", []),
        "overseas_experience": career_split.get("overseas", []),
        # _etc remaining (기타 섹션용)
        "career_etc_remaining": career_split["remaining"],
        "education_etc_remaining": edu_split["remaining"],
        "skills_etc_remaining": skills_split["remaining"],
    }
```

**레거시 필드 호환:** 현재 DB에서 레거시 JSONField가 전부 빈 배열이므로 (`Candidate.objects.filter(projects__len__gt=0).count() == 0`), 레거시 참조를 제거해도 데이터 손실이 없다. 단, `backfill_candidate_details` 커맨드는 레거시 필드에 쓰는 로직이므로, 이 커맨드의 쓰기 대상도 _etc 기반으로 바꾸거나, 더 이상 사용하지 않도록 정리한다.

### 4-F: 템플릿 수정

`candidate_detail_content.html`에서 `candidate.career_etc`를 직접 참조하는 부분을 컨텍스트 변수로 교체:

```
- {% for item in candidate.career_etc %}
+ {% for item in career_etc_remaining %}

- {% for item in candidate.education_etc %}
+ {% for item in education_etc_remaining %}

- {% for item in candidate.skills_etc %}
+ {% for item in skills_etc_remaining %}
```

`trainings_data`, `awards_data`, `patents_data`는 이미 기존 템플릿 변수명과 동일하므로 변경 불필요.

### 수정 파일

```
[ ] candidates/services/etc_normalizer.py — 신규 생성 (split + normalize_* 통과)
[ ] candidates/views.py — _build_etc_context() helper 추가, detail/review 뷰에서 사용
[ ] candidates/templates/.../candidate_detail_content.html — _etc 렌더링 변수 교체
[ ] candidates/management/commands/backfill_candidate_details.py — 레거시 필드 쓰기 정리 (또는 deprecate)
```

### 완료 기준

- 교육훈련/수상/특허 데이터가 `_etc`에서 추출되어 전용 UI 블록에 올바른 shape으로 표시됨
- 기타 섹션에는 분류 안 된 항목만 남음
- 레거시 JSONField (`candidate.projects` 등)를 뷰에서 직접 참조하지 않음
- `uv run pytest -v` 통과

---

## 5단계: 기존 데이터 보정

### 목표

이미 추출된 후보자 데이터에서 `career_etc`에 중복 저장된 퇴사 사유를 정규 Career 레코드로 옮긴다.

### 설계

management command로 일회성 스크립트 실행. 파괴적 변경이 아닌 보강(backfill)만 수행.

### 대상

`career_etc`에서 `type`이 퇴사사유 계열인 항목:
- 해당 회사의 Career 레코드를 **(company + 기간) 복합키**로 매칭
- Career.reason_left가 비어 있으면 description 값을 채움
- 매칭 성공한 항목만 career_etc에서 제거
- **매칭 실패 시 원본 유지** (오매칭으로 인한 영구 오염 방지)

### 매칭 전략

carry-forward와 동일한 복합키 원칙을 적용한다:

1. `_etc` 항목의 `company`/`name`과 `start_date`를 정규화
2. Career 레코드의 `company`와 `start_date`를 정규화
3. 복합키 `(company_normalized, start_date_ym)` 일치 시에만 매칭
4. 복합키 매칭 불가 시 company만으로 매칭하되, **해당 company의 Career가 정확히 1건일 때만** 허용

### 스크립트 위치

`candidates/management/commands/backfill_reason_left.py`

```python
"""career_etc의 퇴사사유 항목을 Career.reason_left로 이관."""
# 구현 시 주의: 아래 private helper들을 직접 import하는 형태는 임시 설계.
# 실제 구현에서는 _normalize_company, _normalize_date_to_ym, _canonicalize 등을
# shared util 모듈(예: candidates/services/matching_utils.py)로 분리하여
# carry-forward, backfill, etc_normalizer가 모두 같은 소스를 사용하도록 한다.
from candidates.services.etc_normalizer import _canonicalize, _CAREER_ETC_ALIASES, _CAREER_ETC_KEYWORDS
from candidates.services.integrity.pipeline import _normalize_company, _normalize_date_to_ym

for candidate in Candidate.objects.filter(career_etc__len__gt=0):
    etc_items = candidate.career_etc or []
    careers = list(candidate.careers.all())
    remaining = []
    changed = False

    for item in etc_items:
        # 4단계 canonicalizer 재사용 — keyword 기반 변형도 잡힘
        if _canonicalize(item, _CAREER_ETC_ALIASES, _CAREER_ETC_KEYWORDS) != "퇴사사유":
            remaining.append(item)
            continue

        etc_company = _normalize_company(item.get("company") or item.get("name") or "")
        etc_date = _normalize_date_to_ym(item.get("start_date") or "")

        matched_career = None

        # 1차: 복합키 매칭
        if etc_company and etc_date:
            for c in careers:
                if _normalize_company(c.company) == etc_company and c.start_date and c.start_date == etc_date:
                    matched_career = c
                    break

        # 2차: company만 매칭 (해당 company Career가 정확히 1건일 때만)
        if not matched_career and etc_company:
            company_matches = [c for c in careers if _normalize_company(c.company) == etc_company]
            if len(company_matches) == 1:
                matched_career = company_matches[0]

        if matched_career and not matched_career.reason_left:
            matched_career.reason_left = item.get("description", "")[:500]
            matched_career.save(update_fields=["reason_left"])
            changed = True
            # 이관 성공 → remaining에 넣지 않음
        else:
            remaining.append(item)  # 매칭 실패 → 원본 유지

    if changed:
        candidate.career_etc = remaining
        candidate.save(update_fields=["career_etc"])
```

### 실행 계획

```bash
# 1. dry-run으로 매칭 결과 확인
uv run python manage.py backfill_reason_left --dry-run

# 2. 실제 실행
uv run python manage.py backfill_reason_left
```

### 재추출 여부

기존 데이터 전체 재추출은 **하지 않는다.** 이유:

- API 비용이 크고
- 기존 추출 결과 중 정상인 것까지 변경될 위험
- backfill 스크립트로 주요 문제(퇴사사유 중복)는 해결 가능

향후 개별 후보자 재추출 시 자연스럽게 개선된 스키마가 적용된다.

### 수정 파일

```
[ ] candidates/management/commands/backfill_reason_left.py — 신규 생성
```

### 완료 기준

- dry-run에서 이관 대상과 매칭 결과 확인
- 실행 후 `career_etc`에서 퇴사사유 type 항목 제거됨
- Career.reason_left에 값이 채워짐
- 상세 페이지에서 중복 표시 해소

---

## 6단계: 검증

### 테스트 대상 후보자

| 후보자 | 검증 포인트 |
|--------|-----------|
| 신지원 | career_etc 퇴사사유 중복 해소 |
| GPA가 있는 후보자 | educations.gpa 추출 여부 |
| 영문 이력서 후보자 | company_en 추출 여부 |
| 수상/특허가 있는 후보자 | _etc에서 전용 UI로 분리 표시 |

### 검증 절차

```bash
# 1. 전체 테스트
uv run pytest -v

# 2. 신지원 재추출 (수동)
uv run python manage.py extract --candidate-id=5c021ea7-cc17-4373-b3d4-9fef5204aedf --force

# 3. 상세 페이지 확인
#    - 경력 섹션: reason_left가 "퇴사 사유 보기" 토글에 표시
#    - 기타 섹션: 퇴사사유 항목 없음
#    - 교육훈련/수상/특허 전용 블록에 _etc에서 분리된 데이터 표시
#    (프로젝트/해외경험은 현재 _etc에 해당 type 데이터가 없으므로 검증 대상 아님)

# 4. regression 확인
#    - 기존에 정상 추출되던 후보자의 상세 페이지가 깨지지 않았는지
#    - _etc 기타 섹션에 원래 있던 진짜 기타 항목이 유지되는지
```

### regression 기준

- 기존 추출 결과가 변경되지 않음 (backfill 대상 제외)
- 4단계 뷰 수정 후 기존에 표시되던 데이터가 사라지지 않음
- 정규 Career/Education 필드에 저장된 값이 변하지 않음

---

## 미결 사항

### 결정 보류

| 항목 | 현재 상태 | 결정 시점 |
|------|----------|----------|
| Education.status 모델 추가 | Step 1에서 추출하지만 DB에 없음 | 6단계 검증 후 필요성 판단 |
| `raw_extracted_json` 전체 구조 전환 | 3-G에서 step1 원본 최소 보존은 포함. 전체 `{step1, step2, final}` 구조 전환은 별도 작업 | 이번 작업 완료 후 |
| 구형 `batch_extract` 경로 정리 | 레거시 스키마 사용 중 | 사용 빈도 확인 후 판단 |
| 레거시 JSONField 모델에서 제거 | save.py에서 빈 배열로 초기화 | 4단계 완료 후 안전하게 제거 가능 |

### 위험 요소

| 위험 | 경감 방안 |
|------|----------|
| Step 1 스키마 변경으로 기존 추출 결과와 구조 불일치 | save.py는 `.get()` 패턴이라 누락 필드에 안전. 신규 필드는 없으면 빈값 처리 |
| `_etc.type` keyword 매칭이 의도치 않은 분류를 만들 수 있음 | keyword 순서 통제 + 실제 분류 결과 로깅. exact match 우선이므로 기존 동작 보존 |
| carry-forward/backfill 오매칭 | (company+start_date) 복합키 사용. 복합키 불일치 시 carry-forward 안 함. backfill은 company 단독 매칭을 Career 1건일 때만 허용. 오매칭보다 누락이 안전 |
| 뷰 수정으로 review_detail도 동시에 영향 | `_build_etc_context()` helper를 detail/review 모두 공유 |
| backfill 후 원본 _etc 항목 영구 제거 | dry-run 필수. 3-G에서 step1 원본이 pipeline_meta에 보존되므로 감사 추적 가능 |
