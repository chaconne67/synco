# 데이터 추출 통합 계획서

**작성일:** 2026-04-05
**목표:** 데이터 추출 관련 모든 코드를 `data_extraction` 앱에 통합한다. `candidates/services/`의 추출 코드는 삭제하고, `batch_extract`는 서비스/커맨드/모델을 제거한 뒤 migration history용 stub 앱으로 축소한다.

---

## 현재 상태

데이터 추출 코드가 3곳에 분산되어 있다:

| 위치 | 역할 | 상태 |
|------|------|------|
| `data_extraction/` | 운영 추출 앱. CLI(`extract`), 파이프라인, 저장 | **주 경로** |
| `candidates/services/integrity/` | 원래 개발된 Step 1/2/3 파이프라인 | 레거시, 삭제 대상 |
| `candidates/services/*.py` | 추출 관련 유틸 (llm_extraction, gemini_extraction 등) | 레거시, 삭제 대상 |
| `batch_extract/` | 배치 추출 전용 앱. 모델(GeminiBatchJob/Item) + 서비스 | 서비스/커맨드/모델은 `data_extraction`으로 흡수 후 제거. migration history용 stub 앱으로 축소 |

### 의존성 방향 문제

현재 `data_extraction`이 `candidates/services/integrity/`를 import하는 역방향 의존이 있다:
- `integrity.py` → `candidates.services.integrity.step1_extract` (스키마, 프롬프트)
- `integrity.py` → `candidates.services.integrity.step2_normalize` (스키마)
- `validators.py` → `candidates.services.integrity.validators`
- `prompts.py` → `candidates.services.integrity.*` (re-export)

이 의존을 끊고, 스키마/프롬프트/validator를 `data_extraction` 안에 직접 정의해야 한다.

---

## 삭제 대상과 잔류 대상

### 삭제 대상 (candidates/services/)

| 파일 | LOC | data_extraction 대응 |
|------|-----|---------------------|
| `integrity/step1_extract.py` | 265 | `extraction/integrity.py`에 이미 동일 코드 |
| `integrity/step1_5_grouping.py` | 163 | `extraction/integrity.py`에 이미 포함 |
| `integrity/step2_normalize.py` | 253 | `extraction/integrity.py`에 이미 동일 코드 |
| `integrity/step3_overlap.py` | 183 | `extraction/integrity.py`에 이미 포함 |
| `integrity/step3_cross_version.py` | 295 | `extraction/integrity.py`에 이미 포함 |
| `integrity/pipeline.py` | 273 | `extraction/integrity.py`에 자체 `run_integrity_pipeline` 있음 |
| `integrity/validators.py` | 218 | `extraction/validators.py`로 이동 |
| `integrity/save.py` | 540 | `save.py`에 이미 동일 코드 |
| `llm_extraction.py` | 218 | `extraction/prompts.py`에 이미 통합 |
| `gemini_extraction.py` | 97 | `extraction/gemini.py`에 이미 통합 |
| `retry_pipeline.py` | 199 | `pipeline.py`에 이미 통합 |
| `validation.py` | 327 | `validation.py`에 이미 통합 |
| `extraction_filters.py` | 176 | `filters.py`에 이미 통합 |
| `drive_sync.py` | 278 | `drive.py`에 이미 통합 |
| `text_extraction.py` | 208 | `text.py`에 이미 통합 |
| `filename_parser.py` | 128 | `filename.py`에 이미 통합 |

### 삭제 대상 (candidates/management/commands/)

| 파일 | 이유 |
|------|------|
| `import_resumes.py` | `extract` 커맨드로 대체됨 |
| `compare_extraction.py` | candidates 추출 서비스에 의존, 삭제 대상 |

### candidates/services/에 남겨야 하는 파일

| 파일 | 이유 |
|------|------|
| `candidate_identity.py` | `Candidate.save()`에서 사용. 추출과 무관한 모델 로직 |
| `discrepancy.py` | `scan_discrepancies` 커맨드 + `save.py`에서 사용. 단, `save.py`가 import하므로 경로 확인 필요 |
| `detail_normalizers.py` | `etc_normalizer.py`, `backfill_candidate_details`에서 사용. 뷰 소비 로직 |
| `salary_parser.py` | `backfill_candidate_details`, `save.py`에서 사용 |
| `etc_normalizer.py` | 뷰에서 `_etc` 분류용. 추출이 아닌 표시 로직 |
| `search.py`, `embedding.py`, `whisper.py` | UI 기능 |

### 삭제 대상 (batch_extract/)

서비스/커맨드/모델은 `data_extraction`으로 이동. migration history용 stub 앱으로 축소.

---

## 삭제 대상 (테스트)

| 테스트 파일 | 이유 | data_extraction 대응 |
|------------|------|---------------------|
| `test_integrity_pipeline.py` | candidates.services.integrity 의존 | `test_de_extraction.py` |
| `test_integrity_validators.py` | 동상 | `test_de_extraction.py` |
| `test_integrity_step1.py` | 동상 | `test_de_extraction.py` |
| `test_integrity_step1_5.py` | 동상 | `test_de_extraction.py` |
| `test_integrity_step2.py` | 동상 | `test_de_extraction.py` |
| `test_integrity_step3.py` | 동상 | `test_de_extraction.py` |
| `test_integrity_cross_version.py` | 동상 | `test_de_extraction.py` |
| `test_llm_extraction.py` | candidates.services.llm_extraction 의존 | `test_de_extraction.py` |
| `test_retry_pipeline.py` | candidates.services.retry_pipeline 의존 | `test_de_pipeline.py` |
| `test_validation.py` | candidates.services.validation 의존 | `test_de_validation.py` |
| `test_extraction_filters.py` | candidates.services.extraction_filters 의존 | `test_de_filters.py` |
| `test_drive_sync.py` | candidates.services.drive_sync 의존 | `test_de_drive.py` |
| `test_text_extraction.py` | candidates.services.text_extraction 의존 | `test_de_text.py` |
| `test_filename_parser.py` | candidates.services.filename_parser 의존 | `test_de_filename.py` |
| `test_import_pipeline.py` | import_resumes 커맨드 의존 | 불필요 |
| `test_save_update_path.py` | candidates.services.integrity.save 의존 | `test_de_save.py` |
| `test_batch_extract_services.py` | batch_extract 의존 | `test_de_batch.py` |

---

## 실행 순서

| 단계 | 작업 | 성격 |
|------|------|------|
| 1 | 스키마/프롬프트를 data_extraction 안에 직접 정의 | import 방향 정리 |
| 2 | carry-forward 로직을 data_extraction/integrity.py에 이식 | 기능 이관 |
| 3 | batch_extract 모델을 data_extraction으로 이동 | 모델 이관 |
| 4 | batch_extract 서비스 import 경로 정리 | import 정리 |
| 5 | 레거시 테스트 삭제 | 정리 (소스 삭제 전에 먼저 제거해야 pytest 통과) |
| 6 | candidates 추출 코드 삭제 | 레거시 제거 |
| 7 | batch_extract 앱 stub 축소 | 레거시 제거 |
| 8 | 검증 | QA |

---

## 1단계: 스키마/프롬프트를 data_extraction 안에 직접 정의

### 목표

`data_extraction`이 `candidates/services/integrity/`를 import하는 역방향 의존을 끊는다.

### 작업

**`data_extraction/services/extraction/prompts.py`:**
- `candidates.services.integrity.step1_extract`에서 re-export하던 `STEP1_SYSTEM_PROMPT`, `STEP1_SCHEMA`를 **직접 정의**로 전환
- `candidates.services.integrity.step2_normalize`에서 re-export하던 `CAREER_*`, `EDUCATION_*`를 **직접 정의**로 전환
- 레거시 `EXTRACTION_SYSTEM_PROMPT`, `EXTRACTION_JSON_SCHEMA`도 이미 여기에 있으므로 유지
- `build_extraction_prompt()`, `build_step1_prompt()` 함수 유지

**`data_extraction/services/extraction/validators.py`:**
- `candidates.services.integrity.validators`에서 re-export하던 것을 **직접 정의**로 전환
- 현재 `candidates` 쪽에 추가한 `raw_careers` 매개변수도 포함

**`data_extraction/services/extraction/integrity.py`:**
- import 경로를 모두 `data_extraction` 내부로 변경:
  - `from data_extraction.services.extraction.prompts import ...`
  - `from data_extraction.services.extraction.validators import ...`

### 소스 복사 방향

| 상수 | 현재 정본 위치 | 복사 대상 |
|------|-------------|----------|
| `STEP1_SYSTEM_PROMPT` | `candidates/.../step1_extract.py:15` | `data_extraction/.../prompts.py` |
| `STEP1_SCHEMA` | `candidates/.../step1_extract.py:130` | `data_extraction/.../prompts.py` |
| `CAREER_SYSTEM_PROMPT` | `candidates/.../step2_normalize.py:12` | `data_extraction/.../prompts.py` |
| `CAREER_OUTPUT_SCHEMA` | `candidates/.../step2_normalize.py:80` | `data_extraction/.../prompts.py` |
| `EDUCATION_SYSTEM_PROMPT` | `candidates/.../step2_normalize.py:108` | `data_extraction/.../prompts.py` |
| `EDUCATION_OUTPUT_SCHEMA` | `candidates/.../step2_normalize.py:149` | `data_extraction/.../prompts.py` |
| `validate_step1()` | `candidates/.../validators.py:32` | `data_extraction/.../validators.py` |
| `validate_step1_5()` | `candidates/.../validators.py:103` | `data_extraction/.../validators.py` |
| `validate_step2()` | `candidates/.../validators.py:141` | `data_extraction/.../validators.py` |

**중요:** 2단계/3단계에서 추가한 필드 보강(reason_left, salary, gpa, level, 날짜 추정 필드 등)과 validator의 `raw_careers` 매개변수도 반드시 포함.

### 완료 기준

- `grep -r "from candidates.services.integrity" data_extraction/` → 0건
- `grep -r "from candidates.services.llm_extraction" data_extraction/` → 0건
- `uv run pytest tests/test_de_*.py -v` 통과

---

## 2단계: carry-forward 로직을 data_extraction/integrity.py에 이식

### 목표

`candidates/services/integrity/pipeline.py`에 추가한 carry-forward 함수와 매칭 유틸을 `data_extraction/services/extraction/integrity.py`에 이식한다.

### 작업

**`data_extraction/services/extraction/integrity.py`에 추가:**

1. `_normalize_company()` — 회사명 정규화
2. `_normalize_date_to_ym()` — 날짜 정규화 (한국어 원문 포함)
3. `_carry_forward_career_fields()` — Step 2 → Step 1 복원 (복합키 매칭)
4. `_carry_forward_education_fields()` — gpa 복원

5. `run_integrity_pipeline()` 수정:
   - carry-forward 호출 추가 (career + education)
   - `pipeline_meta`에 `step1_careers_raw`, `step1_educations_raw` 보존 (임시 전략 주석 포함)
   - `validate_step2()` 호출 시 `raw_careers=careers_raw` 전달

### 현재 data_extraction/integrity.py의 run_integrity_pipeline과 차이점

| 기능 | candidates 버전 | data_extraction 버전 | 조치 |
|------|----------------|---------------------|------|
| carry-forward | O (방금 추가) | X | 이식 |
| step1 원본 보존 | O (pipeline_meta) | X | 이식 |
| validate_step2 raw_careers | O | X | 이식 |
| Step 1.5 grouping | X | O (line 118) | 유지 |
| 날짜 정규화 함수 | O | X | 이식 |

### carry-forward 신규 테스트

`tests/test_de_extraction.py`에 다음 테스트 추가:

1. `test_carry_forward_restores_reason_left` — Step 2가 reason_left를 빠뜨린 경우 Step 1 원본에서 복원되는지
2. `test_carry_forward_composite_key_no_false_match` — 동일 회사 재입사 시 복합키로 올바른 경력에만 매칭
3. `test_carry_forward_education_gpa` — gpa carry-forward
4. `test_normalize_date_to_ym_korean` — `2019년 3월`, `2019년03월`, `2019.03 ~ 현재` 변환
5. `test_validate_step2_detects_field_drop` — `validate_step2(result, raw_careers=...)` 경고 생성

### 완료 기준

- `data_extraction`의 `run_integrity_pipeline()`에 carry-forward 동작 확인
- 위 5개 신규 테스트 통과
- `uv run pytest tests/test_de_extraction.py -v` 통과

---

## 3단계: batch_extract 모델을 data_extraction으로 이동

### 목표

`batch_extract/models.py`의 `GeminiBatchJob`, `GeminiBatchItem`을 `data_extraction/models.py`로 이동한다.

### 마이그레이션 목표

**기존 DB:** 테이블(`gemini_batch_jobs`, `gemini_batch_items`)이 이미 존재. Django state만 `batch_extract` → `data_extraction`으로 이동.
**신규 DB:** 처음부터 `migrate`만으로 테이블이 정상 생성되어야 함.

두 목표를 동시에 만족하려면 **`SeparateDatabaseAndState`**를 사용해야 한다.
단순 `CreateModel`은 기존 DB에서 테이블 생성 SQL을 시도하고, 단순 state-only는 신규 DB에서 테이블을 만들지 못한다.

### 작업

**1. `data_extraction/models.py`에 모델 정의:**
- `GeminiBatchJob`, `GeminiBatchItem` 모델을 `batch_extract/models.py`에서 복사
- `db_table` 유지 (`gemini_batch_jobs`, `gemini_batch_items`)
- `GeminiBatchItem.job` ForeignKey의 `to`를 `data_extraction.GeminiBatchJob`으로 변경
- `GeminiBatchItem.candidate` ForeignKey는 `candidates.Candidate` 유지

**2. migration 생성 (2개 파일):**

`data_extraction/migrations/0002_batch_models.py`:
```python
from django.db import migrations, models
import django.db.models.deletion
import uuid

class Migration(migrations.Migration):
    dependencies = [
        ("data_extraction", "0001_initial"),
        ("batch_extract", "0001_initial"),
        ("candidates", "..."),  # 최신 candidates migration
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # state_operations: Django에게 "이 모델은 이제 data_extraction 앱 소속"이라고 알림
            state_operations=[
                migrations.CreateModel(
                    name="GeminiBatchJob",
                    fields=[...],  # batch_extract/migrations/0001_initial.py에서 복사
                    options={"db_table": "gemini_batch_jobs", ...},
                ),
                migrations.CreateModel(
                    name="GeminiBatchItem",
                    fields=[...],  # job FK를 data_extraction.GeminiBatchJob으로
                    options={"db_table": "gemini_batch_items", ...},
                ),
            ],
            # database_operations: 기존 DB에서는 아무것도 안 함 (테이블 이미 존재)
            # 신규 DB에서는 batch_extract의 0001_initial이 이미 테이블을 생성한 상태
            database_operations=[],
        ),
    ]
```

`batch_extract/migrations/0002_remove_models.py`:
```python
class Migration(migrations.Migration):
    dependencies = [
        ("batch_extract", "0001_initial"),
        ("data_extraction", "0002_batch_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="GeminiBatchItem"),
                migrations.DeleteModel(name="GeminiBatchJob"),
            ],
            database_operations=[],  # 테이블은 그대로 유지
        ),
    ]
```

**이 구조에서:**
- 기존 DB: 테이블 변경 없음. Django state만 업데이트.
- 신규 DB: `batch_extract/0001_initial`이 테이블 생성 → `data_extraction/0002`가 state 이동 → `batch_extract/0002`가 state 제거.
- batch_extract 앱 삭제 후에도 migration history만 남으면 되므로, 7단계에서 stub 앱으로 처리.

**3. `data_extraction/admin.py`에 admin 등록 추가** (batch_extract/admin.py에서 복사)

### 완료 기준

- `uv run python manage.py migrate` 정상 완료
- `uv run python manage.py migrate --check` → 미적용 migration 없음
- `from data_extraction.models import GeminiBatchJob, GeminiBatchItem` 정상
- `GeminiBatchJob.objects.count()` 정상 반환
- `uv run pytest tests/test_de_batch.py -v` 통과

---

## 4단계: batch_extract 서비스 import 경로 정리

### 목표

`data_extraction/services/batch/` 내부 파일들이 `candidates` 서비스나 `batch_extract`를 import하는 곳을 `data_extraction` 내부 경로로 교체한다.

### 작업

**`data_extraction/services/batch/request_builder.py`:**
- `from candidates.services.gemini_extraction import GEMINI_SYSTEM_PROMPT` → `from data_extraction.services.extraction.gemini import GEMINI_SYSTEM_PROMPT`
- `from candidates.services.llm_extraction import build_extraction_prompt` → `from data_extraction.services.extraction.prompts import build_extraction_prompt`

**`data_extraction/services/batch/api.py`:**
- `from batch_extract.models import GeminiBatchJob` → `from data_extraction.models import GeminiBatchJob`

**`data_extraction/services/batch/ingest.py`:**
- `from batch_extract.models import GeminiBatchItem, GeminiBatchJob` → `from data_extraction.models import GeminiBatchItem, GeminiBatchJob`
- `candidates.services.extraction_filters` → `data_extraction.services.filters`
- `candidates.services.integrity.save` → `data_extraction.services.save`
- `candidates.services.validation` → `data_extraction.services.validation`

**`data_extraction/services/batch/prepare.py`:**
- `from batch_extract.models import GeminiBatchItem, GeminiBatchJob` → `from data_extraction.models import GeminiBatchItem, GeminiBatchJob`
- `candidates.services.drive_sync` → `data_extraction.services.drive`
- `candidates.services.filename_parser` → `data_extraction.services.filename`
- `candidates.services.text_extraction` → `data_extraction.services.text`

**`data_extraction/services/save.py`:**
- `candidates.services.discrepancy` import는 유지 (discrepancy는 candidates에 남는 서비스)
- `candidates.services.detail_normalizers` import는 유지 (표시 로직)
- `candidates.services.salary_parser` import는 유지 (표시 로직)
- `candidates.services.candidate_identity` import는 유지 (모델 로직)

**`data_extraction/services/filters.py`:**
- `candidates.services.candidate_identity` import는 유지 (모델 로직)

**`data_extraction/management/commands/extract.py`:**
- `from batch_extract.models import GeminiBatchJob` (3곳: line 569, 577, 749) → `from data_extraction.models import GeminiBatchJob`

**테스트 파일:**
- `tests/test_de_batch.py` — `from batch_extract.models import ...` → `from data_extraction.models import ...`

### 완료 기준

- `grep -r "from batch_extract" data_extraction/` → 0건
- `grep -r "from candidates.services.llm_extraction\|from candidates.services.gemini_extraction\|from candidates.services.retry_pipeline\|from candidates.services.validation\|from candidates.services.extraction_filters\|from candidates.services.drive_sync\|from candidates.services.text_extraction\|from candidates.services.filename_parser\|from candidates.services.integrity" data_extraction/` → 0건
- `uv run pytest tests/test_de_*.py -v` 통과

---

## 5단계: 레거시 테스트 삭제

### 목표

삭제 예정 모듈을 import하는 테스트 파일을 **소스 코드 삭제 전에** 먼저 제거한다.
candidates 추출 코드(6단계)와 batch_extract 서비스(7단계)를 삭제하면 레거시 테스트가 ImportError로 깨지므로, 반드시 이 단계를 먼저 실행한다.

### 삭제 대상

```
tests/test_integrity_pipeline.py
tests/test_integrity_validators.py
tests/test_integrity_step1.py
tests/test_integrity_step1_5.py
tests/test_integrity_step2.py
tests/test_integrity_step3.py
tests/test_integrity_cross_version.py
tests/test_llm_extraction.py
tests/test_retry_pipeline.py
tests/test_validation.py
tests/test_extraction_filters.py
tests/test_drive_sync.py
tests/test_text_extraction.py
tests/test_filename_parser.py
tests/test_import_pipeline.py
tests/test_save_update_path.py
tests/test_batch_extract_services.py
```

### 삭제 전 확인

각 레거시 테스트에 대응하는 `test_de_*` 테스트가 존재하는지 확인:

| 레거시 테스트 | 대응 data_extraction 테스트 | 존재? |
|-------------|---------------------------|------|
| `test_integrity_pipeline.py` | `test_de_extraction.py` | 확인 필요 |
| `test_integrity_step1.py` | `test_de_extraction.py` | 확인 필요 |
| `test_retry_pipeline.py` | `test_de_pipeline.py` | 확인 필요 |
| `test_validation.py` | `test_de_validation.py` | 확인 필요 |
| `test_extraction_filters.py` | `test_de_filters.py` | 확인 필요 |
| `test_save_update_path.py` | `test_de_save.py` | 확인 필요 |
| `test_batch_extract_services.py` | `test_de_batch.py` | 확인 필요 |

대응 테스트가 없으면 삭제하지 않고, `test_de_*`로 이관 후 삭제.

### 완료 기준

- 삭제된 테스트 파일의 테스트 커버리지가 `test_de_*`에 포함됨
- `uv run pytest -v` 전체 통과
- 테스트 수가 대폭 감소하지 않음 (삭제 전/후 비교)

---

## 6단계: candidates 추출 코드 삭제

### 목표

`candidates/services/`에서 추출 전용 파일을 삭제한다.

### 삭제 대상

```
candidates/services/integrity/           # 디렉토리 전체
candidates/services/llm_extraction.py
candidates/services/gemini_extraction.py
candidates/services/retry_pipeline.py
candidates/services/validation.py
candidates/services/extraction_filters.py
candidates/services/drive_sync.py
candidates/services/text_extraction.py
candidates/services/filename_parser.py
```

### 삭제 전 확인

각 파일에 대해 `grep -r "from candidates.services.<filename>" --include="*.py"` 실행.
`data_extraction/` 외의 소비자가 있으면 경로 수정 선행.

**예상 잔류 소비자:**

| 삭제 파일 | 잔류 소비자 | 조치 |
|----------|-----------|------|
| `candidate_identity.py` | **삭제 안 함.** `candidates/models.py`에서 사용 | — |
| `validation.py` | `candidates/views.py`의 `compute_field_confidences` import (2곳: line 124, 367) | 두 곳 모두 `data_extraction.services.validation`으로 변경 |
| `extraction_filters.py` | 없음 (data_extraction에서만 사용) | — |

### candidates/management/commands/ 삭제 대상

```
candidates/management/commands/import_resumes.py
candidates/management/commands/compare_extraction.py
```

### backfill_reason_left.py 수정

`candidates/management/commands/backfill_reason_left.py`가 삭제 대상 파일을 import하고 있다:
- `from candidates.services.integrity.pipeline import _normalize_company, _normalize_date_to_ym`

→ `from data_extraction.services.extraction.integrity import _normalize_company, _normalize_date_to_ym`으로 변경

### 완료 기준

- 삭제된 파일이 import되는 곳 0건
- `candidates/services/integrity/` 디렉토리 없음
- `uv run pytest tests/test_de_*.py tests/test_candidates_*.py tests/test_search_*.py -v` 통과 (레거시 테스트는 5단계에서 이미 삭제됨)

---

## 7단계: batch_extract 앱 stub 축소

### 목표

`batch_extract/` 앱의 서비스/커맨드/모델을 제거하고, migration history 재생을 위한 stub 앱으로 축소한다.

### CLI 호환성 확인

batch_extract에는 5개의 management command가 있다:

| 구 커맨드 | 대체 커맨드 |
|----------|-----------|
| `prepare_resume_batch` | `extract --batch --step prepare` |
| `submit_resume_batch` | `extract --batch --step submit` |
| `run_resume_batch_pipeline` | `extract --batch` |
| `ingest_resume_batch` | `extract --batch --step ingest` |
| `sync_resume_batch` | `extract --batch --step poll` |

**확인 필요:** 운영 스크립트(cron, deploy.sh 등)가 구 커맨드명을 호출하고 있는지.
- 호출자가 없으면 → 즉시 삭제
- 호출자가 있으면 → 구 커맨드를 `call_command('extract', '--batch', ...)`로 래핑하는 deprecation wrapper를 일정 기간 유지

### 작업

1. `grep -r "prepare_resume_batch\|submit_resume_batch\|run_resume_batch_pipeline\|ingest_resume_batch\|sync_resume_batch" --include="*.sh" --include="*.yml" --include="*.yaml" --include="*.toml"` 로 운영 호출자 확인

2. **batch_extract/ → stub 앱으로 축소:**
   ```
   batch_extract/
   ├── __init__.py
   ├── apps.py          # AppConfig만 유지
   └── migrations/
       ├── __init__.py
       ├── 0001_initial.py     # 원본 CreateModel (신규 DB에서 테이블 생성용)
       └── 0002_remove_models.py  # 3단계에서 생성한 state 제거 migration
   ```
   - `models.py`, `admin.py`, `services/` 삭제
   - `management/commands/`:
     - 운영 호출자 없음 → 삭제
     - 운영 호출자 있음 → deprecation wrapper로 전환

3. `main/settings.py` — `INSTALLED_APPS`에 `batch_extract`는 **유지** (migration history 재생을 위해)

4. 향후 모든 DB가 migration을 완료한 뒤, `batch_extract` migration을 `data_extraction`으로 squash하고 stub 앱을 최종 제거 (별도 작업)

### 삭제 전 확인

```bash
# data_extraction 내부에서 batch_extract 참조가 0건인지
grep -r "from batch_extract" data_extraction/ tests/

# batch_extract 내부에서 자기 자신 외 참조가 없는지
grep -r "from batch_extract" --include="*.py" . | grep -v "batch_extract/"
```

### 완료 기준

- `batch_extract/`에 stub 파일만 남음 (`__init__.py`, `apps.py`, `migrations/`)
- `batch_extract/services/`, `batch_extract/models.py`, `batch_extract/admin.py` 삭제됨
- `batch_extract/management/commands/`:
  - 운영 호출자 없음 → 삭제됨
  - 운영 호출자 있음 → deprecation wrapper만 남음
- `uv run python manage.py check` 정상
- `uv run python manage.py migrate --check` 정상
- `uv run pytest -v` 전체 통과

---

## 8단계: 최종 검증

### 작업

```bash
# 1. 전체 테스트
uv run pytest -v

# 2. Django 시스템 체크
uv run python manage.py check

# 3. 미적용 migration 확인
uv run python manage.py showmigrations | grep '\[ \]'

# 4. import 잔류 확인
grep -r "from candidates.services.integrity" --include="*.py" .
grep -r "from candidates.services.llm_extraction\|gemini_extraction\|retry_pipeline\|validation\b\|extraction_filters\|drive_sync\|text_extraction\|filename_parser" --include="*.py" .
grep -r "from batch_extract" --include="*.py" .

# 5. 실제 추출 테스트 (realtime)
uv run python manage.py extract --drive "URL" --limit 1 --integrity

# 6. 배치 경로 테스트
uv run python manage.py extract --batch --status
uv run python manage.py extract --drive "URL" --batch --step prepare --dry-run

# 7. 상세 페이지 확인 (신지원 등)
```

### 완료 기준

- 모든 테스트 통과
- import 잔류 0건
- 실제 추출 + 저장 + 상세 페이지 표시 정상
- `candidates/services/integrity/` 없음
- `batch_extract/`에 stub만 남음 (apps.py + migrations/)

---

## candidates에서 data_extraction이 계속 참조하는 파일

통합 완료 후에도 `data_extraction`이 `candidates`에서 import하는 파일:

| candidates 파일 | data_extraction 소비자 | 이유 |
|----------------|---------------------|------|
| `models.py` | `save.py`, `extract.py` | Candidate, Career, Education 등 모델 |
| `candidate_identity.py` | `filters.py` | `select_primary_phone()` — 전화번호 정규화 |
| `discrepancy.py` | `save.py` | `scan_candidate_discrepancies()` — 검수 보고서 |
| `detail_normalizers.py` | `save.py` | `normalize_military()` 등 — 상세 필드 정규화 |
| `salary_parser.py` | `save.py` | `normalize_salary()` — 연봉 파싱 |

이 파일들은 **추출 로직이 아닌 후보자 모델/표시 로직**이므로 candidates에 남는 것이 맞다.

---

## 위험 요소

| 위험 | 경감 방안 |
|------|----------|
| migration 충돌 | `db_table` 유지로 실제 DB 변경 없음. `SeparateDatabaseAndState` 사용 |
| 삭제 후 숨은 import 깨짐 | 각 단계마다 `grep` + `pytest` 실행. 단계별 커밋 |
| 레거시 테스트 삭제로 커버리지 감소 | 삭제 전 `test_de_*` 대응 확인. 대응 없으면 이관 |
| batch_extract admin 페이지 소실 | data_extraction/admin.py에 등록 복사 |
| `backfill_reason_left.py`의 import 깨짐 | 6단계에서 경로 변경 포함 |
| `candidates/views.py`의 validation import 깨짐 | 6단계에서 경로 변경 포함 |
