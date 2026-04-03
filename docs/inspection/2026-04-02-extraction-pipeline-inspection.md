# 데이터 추출 파이프라인 점검 보고서

**일자:** 2026-04-02
**범위:** 이력서 임포트 전체 파이프라인 (Google Drive -> 텍스트 추출 -> Gemini LLM -> 검증 -> DB 저장)
**점검자:** Claude (자동 코드 점검)

---

## 1. 요약

파이프라인 전체가 **정상 작동 가능한 상태**이며, 리팩토링(Codex 삭제, Few-shot 삭제, Gemini 전환)이 깨끗하게 완료되었다. 다만 `compare_extraction.py`에 존재하지 않는 함수를 참조하는 **런타임 에러 1건**, 날짜 포맷 불일치로 인한 **검증 우회 1건**, 필드 길이 불일치 **1건**이 발견되었다.

---

## 2. 아키텍처 다이어그램 (현재 상태)

```
import_resumes.py (진입점, Django management command)
    |
    |-- drive_sync.py          Google Drive OAuth + 파일 목록/다운로드
    |-- filename_parser.py     파일명에서 이름/생년 파싱 + 인물별 그룹핑
    |
    v
[다운로드된 .doc/.docx 파일]
    |
    |-- text_extraction.py     python-docx / antiword / LibreOffice 텍스트 추출
    |       + preprocess_resume_text()  중복/노이즈 제거 (25-40% 토큰 절감)
    |
    v
[전처리된 텍스트]
    |
    |-- retry_pipeline.py      추출 + 검증 오케스트레이션 (1회 시도, 재시도 없음)
    |       |
    |       |-- gemini_extraction.py   Gemini 3.1 Flash Lite로 구조화 JSON 추출
    |       |       |
    |       |       +-- llm_extraction.py   프롬프트/스키마 정의 원천 (EXTRACTION_SYSTEM_PROMPT,
    |       |                               build_extraction_prompt, EXTRACTION_JSON_SCHEMA)
    |       |
    |       +-- validation.py          rule-based 검증 + 파일명 교차 검증 + 신뢰도 점수
    |
    v
[추출 결과 + 검증 진단]
    |
    |-- detail_normalizers.py  상세 필드 정규화 (군복무, 수상, 해외, 자기소개 등)
    |-- salary_parser.py       연봉 파싱 (만원 단위 정규화)
    |
    v
[DB 저장: Candidate, Education, Career, Certification, LanguageSkill,
          Resume, ExtractionLog, ValidationDiagnosis]


=== 별도 경로 (범용 LLM) ===

common/llm.py  -----> Claude CLI (subprocess) 또는 OpenAI-compatible API
    ^                  검색(search.py), 작업 감지(task_detect.py) 등 범용 용도
    |
    +-- llm_extraction.py의 extract_candidate_data()  (legacy, compare_extraction에서만 사용)


=== 보조 커맨드 ===

compare_extraction.py     Sonnet vs Gemini 비교 (별도 실행)
generate_embeddings.py    Gemini embedding 생성
backfill_candidate_details.py  기존 후보자 상세 필드 백필
```

---

## 3. 점검 결과

### A. 아키텍처 정합성

| 항목 | 결과 | 상세 |
|------|------|------|
| 데이터 추출은 Gemini 3.1만 사용하는가? | **PASS** | `retry_pipeline.py:7`에서 `gemini_extraction.extract_candidate_data`를 직접 import. Claude가 추출에 개입하지 않음. |
| 범용 LLM 호출은 Claude CLI를 사용하는가? | **PASS** | `common/llm.py`는 기본 provider `claude_cli`로 subprocess 호출. 검색/작업감지에서만 사용. |
| 두 경로가 명확하게 분리되어 있는가? | **PASS** | Gemini(추출) vs Claude CLI(범용)가 import 레벨에서 완전 분리. |
| 삭제된 모듈에 대한 잔여 참조가 없는가? | **PASS** | `codex_validation`, `fewshot_store`, `ParseExample`에 대한 import/참조 없음. migration 파일에만 `ParseExample` 이름이 남아있으나 정상(migration 히스토리). |
| Dead code가 없는가? | **WARNING** | 아래 발견 목록 참조 (2건) |

### B. 데이터 흐름 검증

| 항목 | 결과 | 상세 |
|------|------|------|
| import_resumes -> retry_pipeline -> gemini_extraction -> validation 흐름 | **PASS** | `import_resumes.py:314` -> `run_extraction_with_retry()` -> `extract_candidate_data()` -> `validate_extraction()`. 끊김 없음. |
| retry_pipeline 반환값 구조 | **PASS** | `{extracted, diagnosis, attempts, retry_action, raw_text_used}` 구조가 `import_resumes.py:314-329`에서 올바르게 소비됨. |
| validation.py 반환값 변환 | **PASS** | `validate_extraction()` -> `{confidence_score, validation_status, field_confidences, issues}` -> `retry_pipeline`에서 `diagnosis` dict로 재구성 -> `import_resumes`에서 올바르게 사용. |
| DB 저장 시 필수 필드 | **PASS** | `Candidate`, `Resume`, `Education`, `Career`, `Certification`, `LanguageSkill`, `ExtractionLog`, `ValidationDiagnosis` 모든 필수 필드가 채워짐. `_t()` 함수로 varchar overflow 방지. |

### C. 에러 핸들링

| 항목 | 결과 | 상세 |
|------|------|------|
| Gemini API 실패 시 처리 | **PASS** | `gemini_extraction.py:52-92`: 3회 재시도 + `None` 반환 -> `retry_pipeline`에서 `None` 감지 -> `import_resumes._process_group`에서 `_save_failed_resume()` 호출. |
| 텍스트 추출 실패 시 처리 | **PASS** | `import_resumes.py:308-309`: 빈 텍스트 체크 후 `_save_failed_resume()` 호출. `text_extraction.py`에서 docx 실패 시 LibreOffice fallback. |
| 빈 텍스트 / 잘못된 JSON | **PASS** | `gemini_extraction.py:75-81`: dict 아닌 응답, `name` 키 없는 응답 체크. JSON 파싱 실패 시 exception -> retry. |
| ValidationDiagnosis 저장 | **PASS** | `import_resumes.py:414-423`: 모든 필수 필드(`candidate`, `resume`, `attempt_number`, `verdict`, `overall_score`, `issues`, `field_scores`, `retry_action`) 채워짐. |
| Drive 다운로드 실패 | **PASS** | `drive_sync.py:176-197`: 3회 재시도 + 지수 백오프. |
| ThreadPoolExecutor 예외 처리 | **PASS** | `import_resumes.py:273-275`: `future.result()` 호출 시 `except Exception`으로 포착. |

### D. 코드 품질

| 항목 | 결과 | 상세 |
|------|------|------|
| 미사용 import | **PASS** | 모든 서비스 모듈의 import가 실제 사용됨. |
| 잘못된 docstring | **WARNING** | `validation.py:1` - "3-layer validation" 이라고 하지만, LLM 별도 호출 layer는 없음. 실제로는 2-layer (rule-based + cross-check) + LLM이 반환한 field_confidences를 합산하는 구조. 혼동 가능. |
| 타입 힌트 정합성 | **PASS** | 주요 함수 모두 타입 힌트 완비. `retry_pipeline.run_extraction_with_retry` 반환 타입 `dict`은 정확하지만 TypedDict로 하면 더 좋음. |
| 하드코딩된 값 | **INFO** | `gemini_extraction.py:27` - `GEMINI_MODEL = "gemini-3.1-flash-lite-preview"` 상수로 관리됨. 적절함. |
| `_t()` 함수 위치 | **INFO** | `import_resumes.py:23-25` - 모듈 최상위에 `_t()` helper 정의. `from __future__ import annotations` 아래에 위치하나 다른 import보다 위에 있어 PEP 8 위반(import 순서). 기능상 문제 없음. |

### E. 테스트 커버리지

| 항목 | 결과 | 상세 |
|------|------|------|
| gemini_extraction.py 테스트 | **FAIL** | 테스트 파일 없음 (`tests/test_gemini_extraction.py` 부재). 메인 추출 엔진임에도 직접 테스트가 없음. |
| 삭제된 기능의 잔여 테스트 | **PASS** | codex_validation, fewshot_store 관련 테스트 없음. 깨끗하게 정리됨. |
| mock 대상 정합성 | **PASS** | `test_retry_pipeline.py`에서 `retry_pipeline.extract_candidate_data`를 mock (gemini_extraction에서 import된 것). 올바름. `test_llm_extraction.py`에서 `llm_extraction.call_llm_json`을 mock. 올바름. |
| test_llm_extraction.py 용도 | **INFO** | legacy Sonnet 추출 함수 테스트. `llm_extraction.py`가 `compare_extraction.py`에서 사용되므로 테스트 유지 적절. |
| 전체 테스트 결과 | **PASS** | 51개 테스트 전부 통과 (3.58s). |

### F. 보안/설정

| 항목 | 결과 | 상세 |
|------|------|------|
| API 키 하드코딩 | **PASS** | Gemini: 환경변수 사용. Google OAuth 토큰/시크릿도 settings 기반 경로(`GOOGLE_TOKEN_PATH`, `GOOGLE_CLIENT_SECRET_PATH`)로 설정 가능. |
| 환경변수 누락 시 에러 메시지 | **PASS** | `gemini_extraction.py:31-32`: `GEMINI_API_KEY` 미설정 시 `RuntimeError("GEMINI_API_KEY not set in environment")` 명확한 메시지. |
| API 키 접근 방식 불일치 | **WARNING** | `gemini_extraction.py:30`은 `os.environ.get()`으로 직접 접근하지만, `common/embedding.py:16`은 `settings.GEMINI_API_KEY`로 접근. 동일한 키인데 경로가 다름. `settings.py:116`에서 `os.environ.get("GEMINI_API_KEY", "")`로 정의되어 있어 값은 동일하지만, 일관성 부재. |

---

## 4. 발견된 문제 목록

### CRITICAL

#### C-1. `compare_extraction.py`에서 존재하지 않는 함수 참조

- **파일:** `candidates/management/commands/compare_extraction.py:53`
- **내용:** `"import": ("candidates.services.gemini_extraction", "extract_with_gemini")` 로 되어 있으나, `gemini_extraction.py`에 `extract_with_gemini`라는 함수는 없음. 실제 함수명은 `extract_candidate_data`.
- **영향:** `uv run python manage.py compare_extraction --models gemini` 실행 시 `AttributeError` 발생.
- **심각도:** critical (기능 불능)

### WARNING

#### W-1. 날짜 포맷 불일치로 경력 날짜 순서 검증 우회

- **파일:** `candidates/services/validation.py:13` (`_date_to_number`)
- **내용:** `_date_to_number()`은 `.` (dot) 구분자만 파싱 (예: `2020.03`). 그런데 LLM 스키마(`llm_extraction.py:55-56`)에서는 `YYYY-MM` (hyphen) 형식을 요청. Gemini가 `2020-03` 형식으로 반환하면 `_date_to_number`이 `None`을 반환하여 경력 날짜 순서 검증이 **완전히 무시**됨.
- **영향:** start_date > end_date인 비정상 경력 데이터가 warning 없이 통과.
- **심각도:** warning (데이터 품질 저하)

#### W-2. `_t()` 함수의 truncation 길이가 DB `max_length`보다 큰 필드들

- **파일:** `candidates/management/commands/import_resumes.py:528`, `561`
- **내용:**
  - `Education.institution`: DB `max_length=100` vs `_t(값, 200)` -> 101~200자 데이터가 DB에 저장 시도되면 `DataError` 발생 가능
  - `Education.major`: DB `max_length=100` vs `_t(값, 200)` -> 동일 문제
  - `Certification.name`: DB `max_length=100` vs `_t(값, 200)` -> 동일 문제
  - `Certification.issuer`: DB `max_length=100` vs `_t(값, 200)` -> 동일 문제
- **영향:** LLM이 긴 값을 반환할 경우 `django.db.utils.DataError: value too long` 발생 가능. 실제로는 드물지만 방어 코드의 의도와 불일치.
- **심각도:** warning (잠재적 런타임 에러)

#### W-3. `validation.py` 모듈 docstring이 현재 구조와 불일치

- **파일:** `candidates/services/validation.py:1`
- **내용:** `"""3-layer validation for resume extraction: LLM confidence + rule-based + cross-check."""` 라고 되어 있으나, 실제로는 별도 LLM 호출 layer가 없음. 추출 결과에 포함된 `field_confidences`를 사용하는 것이지 독립적인 LLM 검증 layer가 아님.
- **영향:** 코드 이해에 혼동 유발.
- **심각도:** warning (유지보수성)

#### W-4. `extraction_rules.json` 미사용 (dead code)

- **파일:** `candidates/services/extraction_rules.json`
- **내용:** 파일이 존재하지만 어떤 Python 코드에서도 import/load하지 않음. self-evolving pipeline 설계 문서에서 참조되지만, 실제 구현에 연결되지 않은 채 방치됨.
- **영향:** 없음 (기능에 영향 없음). 코드베이스 혼잡도 증가.
- **심각도:** warning (dead artifact)

#### W-5. `llm_extraction.py`의 legacy 함수 docstring 부정확

- **파일:** `candidates/services/llm_extraction.py:102-105`
- **내용:** docstring에 `"Uses Claude Sonnet"` 이라고 되어 있으나, 실제로는 `common/llm.py`를 통해 설정된 provider(기본 `claude_cli`)를 사용. "Sonnet"이 아니라 `common/llm.py`의 provider 설정에 따라 달라짐. 또한 `claude_cli`가 `--model sonnet`을 하드코딩하고 있어 결국 Sonnet이 맞긴 하지만, 설명이 추상화 레벨과 맞지 않음.
- **심각도:** warning (유지보수성)

### INFO

#### I-1. `gemini_extraction.py`에 대한 직접 단위 테스트 부재

- **파일:** `tests/` 디렉토리
- **내용:** 메인 추출 엔진(`gemini_extraction.py`)에 대한 전용 테스트 파일이 없음. `test_retry_pipeline.py`에서 mock을 통해 간접 테스트되지만, JSON 파싱 로직, 마크다운 블록 추출, 재시도 로직 등이 직접 테스트되지 않음.
- **영향:** 리그레션 감지 능력 저하.

#### I-2. GEMINI_API_KEY 접근 경로 불일치

- **파일:** `candidates/services/gemini_extraction.py:30` vs `common/embedding.py:16`
- **내용:** `gemini_extraction.py`는 `os.environ.get("GEMINI_API_KEY")`, `embedding.py`는 `settings.GEMINI_API_KEY`. 동일한 값이지만 접근 경로가 다름. Django settings를 통한 일관된 접근이 바람직.

#### I-3. JSON 스키마에 상세 필드(salary, military 등) 미포함

- **파일:** `candidates/services/llm_extraction.py:25-86` (`EXTRACTION_JSON_SCHEMA`)
- **내용:** 프롬프트의 JSON 스키마에 salary, military_service, awards, overseas_experience, self_introduction, family_info, trainings, patents, projects 필드가 포함되어 있지 않음. LLM이 이력서에서 자체적으로 이런 필드를 반환할 수 있지만, 스키마에 명시하지 않으면 일관성이 떨어짐. `import_resumes.py`의 `_create_candidate()`에서 `extracted.get("military_service")` 등으로 접근하나, LLM이 항상 이 키를 반환하리라는 보장 없음.
- **영향:** 상세 필드 추출 일관성 저하. `normalize_*` 함수들이 다양한 키 이름을 fallback으로 처리하므로 현재로서는 동작하지만, 스키마에 명시하면 추출 품질이 향상될 수 있음.

#### I-4. `_t()` 함수가 import 문 사이에 위치

- **파일:** `candidates/management/commands/import_resumes.py:23-25`
- **내용:** `from __future__ import annotations` 다음, 나머지 import 전에 `_t()` 함수가 정의됨. PEP 8 import 순서 위반. `ruff`가 경고하지 않는 이유는 함수 정의이지 import가 아니기 때문이나, 코드 가독성에 좋지 않음.

#### I-5. `retry_pipeline.py`의 이름과 실제 동작 불일치

- **파일:** `candidates/services/retry_pipeline.py`
- **내용:** 파일명이 `retry_pipeline`이지만 실제로는 재시도 로직이 없음 (1회 시도). `gemini_extraction.py` 내부에 3회 재시도가 있고, `retry_pipeline`은 추출 + 검증을 조합하는 오케스트레이터 역할만 함. `extraction_pipeline.py`가 더 적절한 이름.

---

## 5. 수정 필요 사항

### 즉시 수정 (Critical)

| # | 파일:라인 | 수정 내용 |
|---|-----------|-----------|
| 1 | `candidates/management/commands/compare_extraction.py:53` | `"extract_with_gemini"` -> `"extract_candidate_data"`로 변경 |

### 권장 수정 (Warning)

| # | 파일:라인 | 수정 내용 |
|---|-----------|-----------|
| 2 | `candidates/services/validation.py:13` | `_date_to_number()`에서 `.` 뿐만 아니라 `-` 구분자도 파싱하도록 수정. 예: `parts = date_str.strip().replace("-", ".").split(".")` |
| 3 | `candidates/management/commands/import_resumes.py:528` | `_t(edu.get("institution"), 200)` -> `_t(edu.get("institution"), 100)` (DB max_length=100에 맞춤) |
| 4 | `candidates/management/commands/import_resumes.py:530` | `_t(edu.get("major"), 200)` -> `_t(edu.get("major"), 100)` |
| 5 | `candidates/management/commands/import_resumes.py:561` | `_t(cert.get("name"), 200)` -> `_t(cert.get("name"), 100)` |
| 6 | `candidates/management/commands/import_resumes.py:562` | `_t(cert.get("issuer"), 200)` -> `_t(cert.get("issuer"), 100)` |
| 7 | `candidates/services/validation.py:1` | docstring을 `"""Rule-based validation for resume extraction: data rules + filename cross-check."""`로 변경 |
| 8 | `candidates/services/extraction_rules.json` | 사용 계획이 없으면 삭제, 또는 코드에서 활용하도록 연결 |

### 개선 권장 (Info)

| # | 파일 | 수정 내용 |
|---|------|-----------|
| 9 | `tests/test_gemini_extraction.py` (신규) | `gemini_extraction.py`의 JSON 파싱, 마크다운 블록 추출, 재시도, 에러 처리에 대한 단위 테스트 추가 |
| 10 | `candidates/services/gemini_extraction.py:30` | `os.environ.get("GEMINI_API_KEY")` -> `settings.GEMINI_API_KEY`로 변경하여 `embedding.py`와 일관성 확보 |
| 11 | `candidates/services/llm_extraction.py:25-86` | `EXTRACTION_JSON_SCHEMA`에 salary, military_service, awards, overseas_experience, self_introduction, family_info, trainings, patents, projects 필드 추가 고려 |
| 12 | `candidates/services/retry_pipeline.py` | 파일명을 `extraction_pipeline.py`로 변경 고려 (breaking change이므로 import 전체 수정 필요) |
