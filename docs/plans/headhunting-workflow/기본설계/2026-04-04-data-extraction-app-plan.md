# data_extraction 앱 통합 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이력서 데이터 추출 파이프라인을 `data_extraction` 앱 하나로 통합. `candidates`와 `batch_extract`에 흩어진 추출 로직을 모으고, 실시간/배치 처리를 하나의 파이프라인에서 옵션으로 선택.

**Architecture:** 4단계 파이프라인 (수집 → 추출 → 검증 → 저장)을 독립 모듈로 분리. 실시간 모드(Gemini API 직접 호출)와 배치 모드(Gemini Batch API JSONL 제출)를 같은 인터페이스로 제공. 모델은 `candidates.models`를 그대로 참조 (외래키 관계 유지). 도메인 로직(동일인 매칭, 전화번호 정규화, 일관성 검사)은 `candidates`에 남기고, `data_extraction`이 이를 임포트.

**Tech Stack:** Django 5.2, Gemini API, Google Drive API, ThreadPoolExecutor

---

## 현재 상태

### 문제점

1. **추출 로직이 두 앱에 분산** — `candidates/services/`에 15개 모듈, `batch_extract/services/`에 5개 모듈이 같은 파이프라인의 다른 실행 경로
2. **공유 코드의 방향이 역전** — `batch_extract`가 `candidates.services`를 임포트하는 구조. `candidates`는 UI+모델 앱인데 추출 로직의 소유자가 됨
3. **하드코딩 중복** — 프롬프트, 검증 규칙, 정규화 로직이 실시간/배치 경로에서 각각 관리
4. **폴더 순회 방식 불일치** — `import_resumes`는 병렬 탐색, `batch_extract`는 순차 탐색

### 이전 관계

```
candidates/services/  ←── batch_extract/services/ (역방향 의존)
candidates/models.py  ←── batch_extract/models.py (정상)
```

### 목표 관계

```
data_extraction/services/  (추출 파이프라인)
  ↓ 임포트
candidates/services/       (도메인 로직: identity, discrepancy, normalizers)
candidates/models.py       (Candidate, Resume, Career 등 도메인 모델)
```

### 코드 분류: 이동 vs 잔류

**`data_extraction`으로 이동 (추출 파이프라인 전용):**
- `drive_sync.py` — Drive API 연동
- `text_extraction.py` — 파일 → 텍스트 변환
- `filename_parser.py` — 파일명 파싱, 그룹핑
- `extraction_filters.py` — LLM 출력 정규화
- `gemini_extraction.py` — Gemini API 호출
- `llm_extraction.py` — 프롬프트, 스키마
- `retry_pipeline.py` — 추출 오케스트레이터
- `validation.py` — 추출 결과 검증
- `integrity/` — 무결성 파이프라인 전체
- `batch_extract/` — 배치 처리 전체

**`candidates`에 잔류 (도메인 로직, 다른 코드가 직접 사용):**
- `candidate_identity.py` — `Candidate.save()`에서 `normalize_phone_for_matching()` 호출. 이동 시 역의존 발생
- `discrepancy.py` — `scan_discrepancies` 커맨드에서 직접 사용
- `detail_normalizers.py` — `backfill_candidate_details` 커맨드에서 직접 사용
- `salary_parser.py` — `backfill_candidate_details` 커맨드에서 직접 사용
- `search.py`, `embedding.py`, `whisper.py` — UI 기능

---

## 마이그레이션 원칙

1. **기존 코드를 건드리지 않는다** — `candidates/services/`, `batch_extract/` 기존 파일을 수정/삭제하지 않음. 새 앱에서 새로 작성.
2. **도메인 로직은 `candidates`에 남긴다** — `candidate_identity.py`, `discrepancy.py`, `detail_normalizers.py`, `salary_parser.py`는 이동하지 않음. `data_extraction`이 이들을 임포트.
3. **배치 모델은 앱 소유권 이전** — `db_table` 재매핑이 아닌 `SeparateDatabaseAndState` 마이그레이션으로 앱 라벨 이전.
4. **테스트가 전부 통과한 후에만 삭제** — 새 앱의 테스트가 기존 테스트와 동일하게 통과하면, 그때 기존 코드 삭제 작업을 별도로 진행.
5. **새 import 경로 전용 테스트 작성** — 기존 테스트는 `candidates.services.*`를 임포트하므로, `data_extraction.*` 경로가 정상 동작하는지 별도 테스트가 필수.
6. **커맨드 이름은 새로 정한다** — `import_resumes` → `extract`, 통합된 단일 진입점.

---

## 파일 구조

```
data_extraction/
├── __init__.py
├── apps.py
├── models.py                         # 공존 기간: 비어 있음 (batch_extract.models 임포트). Task 11에서 모델 이전
├── admin.py
├── management/
│   └── commands/
│       └── extract.py                # 통합 CLI 진입점
├── services/
│   ├── __init__.py
│   ├── drive.py                      # Drive 연동 (discover, list, download)
│   ├── text.py                       # 텍스트 추출 (.doc, .docx → plain text)
│   ├── filename.py                   # 파일명 파싱, 사람 단위 그룹핑
│   ├── filters.py                    # LLM 출력 정규화 (email, phone, date, gender)
│   ├── pipeline.py                   # 실시간 파이프라인 오케스트레이터
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── gemini.py                 # Gemini API 단건 호출
│   │   ├── prompts.py                # 추출 프롬프트 (시스템/유저)
│   │   ├── integrity.py              # 3단계 무결성 파이프라인
│   │   └── validators.py             # 파이프라인 단계별 검증
│   ├── validation.py                 # 추출 결과 규칙 검증 + 신뢰도 점수
│   ├── save.py                       # DB 저장 (Candidate, Resume, 하위 레코드)
│   └── batch/
│       ├── __init__.py
│       ├── prepare.py                # JSONL 요청 파일 생성
│       ├── request_builder.py        # JSONL 한 줄 생성 + 응답 파싱
│       ├── api.py                    # Gemini Batch API (upload, submit, poll, download)
│       ├── ingest.py                 # 배치 결과 파싱 → 검증 → DB 저장
│       └── artifacts.py              # 배치 파일 경로 관리
└── migrations/
    ├── 0001_initial.py               # batch_extract에서 앱 라벨 이전 (state-only)
    └── ...
```

### 파일별 소스 매핑

| 새 파일 | 원본 소스 | 변경 사항 |
|---------|----------|----------|
| `services/drive.py` | `candidates/services/drive_sync.py` | `discover_folders()`, `list_all_files_parallel()`, `parse_drive_id()` 포함. `CATEGORY_FOLDERS` 제거 |
| `services/text.py` | `candidates/services/text_extraction.py` | 변경 없음 |
| `services/filename.py` | `candidates/services/filename_parser.py` | 변경 없음 |
| `services/filters.py` | `candidates/services/extraction_filters.py` | `candidates.services.candidate_identity`에서 `select_primary_phone` 임포트 (잔류 모듈 참조) |
| `services/extraction/gemini.py` | `candidates/services/gemini_extraction.py` | 프롬프트를 `prompts.py`로 분리 |
| `services/extraction/prompts.py` | `candidates/services/llm_extraction.py` + `integrity/step1_extract.py` | 모든 프롬프트 통합 관리 |
| `services/extraction/integrity.py` | `candidates/services/integrity/pipeline.py` + `step1_extract.py` + `step2_normalize.py` + `step3_*.py` | 3단계 파이프라인 하나의 모듈로 통합 |
| `services/extraction/validators.py` | `candidates/services/integrity/validators.py` | 변경 없음 |
| `services/validation.py` | `candidates/services/validation.py` | 변경 없음 |
| `services/save.py` | `candidates/services/integrity/save.py` | `candidates.services.detail_normalizers`, `candidates.services.salary_parser`, `candidates.services.candidate_identity`, `candidates.services.discrepancy` 임포트 (잔류 모듈 참조) |
| `services/pipeline.py` | `candidates/services/retry_pipeline.py` | 실시간 추출 오케스트레이터 |
| `services/batch/prepare.py` | `batch_extract/services/prepare.py` | 새 `drive.py`, `text.py`, `filename.py` 사용 |
| `services/batch/request_builder.py` | `batch_extract/services/request_builder.py` | `prompts.py`에서 프롬프트 임포트 |
| `services/batch/api.py` | `batch_extract/services/gemini_batch.py` | 변경 없음 |
| `services/batch/ingest.py` | `batch_extract/services/ingest.py` | 새 `filters.py`, `validation.py`, `save.py`, `request_builder.py` 사용 |
| `services/batch/artifacts.py` | `batch_extract/services/artifacts.py` | 경로를 `.data_extraction/`으로 변경 |
| `management/commands/extract.py` | 신규 | 통합 CLI |
| `models.py` | 공존 기간: 비어 있음. Task 11에서 `batch_extract/models.py` 이전 | Phase I: `from batch_extract.models import ...`. Phase II: 모델 직접 정의 |

---

## 통합 CLI 설계

### 실시간 모드 (기본)

```bash
# Google Drive URL로 전체 폴더 처리
uv run python manage.py extract --drive "https://drive.google.com/drive/folders/1gPM..."

# 특정 하위 폴더만
uv run python manage.py extract --drive "URL" --folder HR

# 병렬 워커 수 조정
uv run python manage.py extract --drive "URL" --workers 10

# 무결성 파이프라인 사용
uv run python manage.py extract --drive "URL" --integrity

# 건수 제한
uv run python manage.py extract --drive "URL" --limit 50

# 미리보기
uv run python manage.py extract --drive "URL" --dry-run
```

### 배치 모드

```bash
# 전체 파이프라인 한번에 (prepare → submit → poll → ingest)
uv run python manage.py extract --drive "URL" --batch

# 단계별 실행
uv run python manage.py extract --drive "URL" --batch --step prepare
uv run python manage.py extract --batch --step submit --job-id 3
uv run python manage.py extract --batch --step poll --job-id 3
uv run python manage.py extract --batch --step ingest --job-id 3

# 배치 작업 목록/상태 확인
uv run python manage.py extract --batch --status
```

### `--job-id` 규칙

- `--step prepare`: `--drive` 필수, `--job-id` 불필요 (새 job 생성)
- `--step submit|poll|ingest`: `--job-id` 필수 (어떤 job인지 명시)
- `--batch` 단독 (단계 미지정): prepare가 job 생성 → 이후 단계에 자동 전달
- `--status`: job 목록 출력, `--job-id` 없으면 최근 10개

### 공통 4단계 파이프라인

두 모드 모두 같은 단계를 거침. 차이는 Phase B(LLM 추출)의 실행 방식뿐.

```
Phase A: 수집 (Drive 탐색 → 파일 목록 → 다운로드 → 텍스트 추출)
  ├─ 실시간: ThreadPoolExecutor로 다운로드+텍스트 추출 병렬
  └─ 배치:   동일

Phase B: LLM 추출 (텍스트 → 구조화 JSON)
  ├─ 실시간: Gemini API 직접 호출 (ThreadPoolExecutor)
  └─ 배치:   JSONL 제출 → Gemini Batch API → 결과 다운로드

Phase C: 검증 (규칙 검증 + 정규화 필터 + 동일인 매칭)
  ├─ 실시간: 추출 직후 즉시 실행
  └─ 배치:   ingest 단계에서 실행

Phase D: 저장 (Candidate, Resume, Career 등 DB 저장)
  ├─ 실시간: 건별 트랜잭션
  └─ 배치:   건별 트랜잭션 (동일)
```

---

## 작업 순서

### Task 1: 앱 뼈대 + 배치 모델 앱 라벨 이전

**Files:**
- Create: `data_extraction/__init__.py`
- Create: `data_extraction/apps.py`
- Create: `data_extraction/models.py`
- Create: `data_extraction/admin.py`
- Create: `data_extraction/migrations/0001_initial.py` (state-only migration)
- Modify: `main/settings.py` — `INSTALLED_APPS`에 `data_extraction` 추가

**배치 모델 전략 (2단계):**

배치 모델(`GeminiBatchJob`, `GeminiBatchItem`)은 공존 기간에 복제하지 않음. 같은 `db_table`을 두 앱에서 동시에 정의하면 Django 모델 로딩, admin 등록, 마이그레이션 모두 충돌.

**Phase I (Task 1~10, 공존 기간):** `data_extraction`에 배치 모델을 만들지 않음
- `data_extraction`의 배치 서비스는 `from batch_extract.models import GeminiBatchJob, GeminiBatchItem`으로 기존 모델 직접 사용
- `batch_extract` 코드/마이그레이션/모델 변경 없음
- `data_extraction/models.py`는 비어 있음 (또는 추출 전용 모델만 필요 시 추가)
- `data_extraction/migrations/0001_initial.py`는 빈 마이그레이션 (앱 등록용)

**Phase II (Task 11, `batch_extract` 삭제 시점):** 모델 이전 + fresh DB 지원
- `data_extraction/models.py`에 `GeminiBatchJob`, `GeminiBatchItem` 정의
- `data_extraction/migrations/`에 실제 `CreateModel` 포함 마이그레이션 추가
- 기존 DB: `SeparateDatabaseAndState`로 state만 전환 (테이블 이미 존재)
- fresh DB: 실제 `CreateModel`로 테이블 생성
- `batch_extract/` 디렉토리 삭제
- `django_migrations`에서 `batch_extract` 항목은 `manage.py migrate --prune`으로 정리

**Steps:**

- [ ] Step 1: Django 앱 생성 (`startapp data_extraction`)
- [ ] Step 2: `apps.py`에 `DataExtractionConfig` 설정
- [ ] Step 3: `models.py`는 비워둠 (배치 모델은 공존 기간에 `batch_extract.models`에서 임포트)
- [ ] Step 4: `data_extraction/migrations/0001_initial.py` — 빈 마이그레이션 (앱 등록용)
- [ ] Step 5: `main/settings.py`에 `data_extraction` 앱 등록
- [ ] Step 6: `manage.py migrate` 실행, `manage.py check` — 충돌 없음 확인
- [ ] Step 7: 커밋

---

### Task 2: 기반 서비스 이식 (순수 로직, 외부 의존 없음)

**Files:**
- Create: `data_extraction/services/__init__.py`
- Create: `data_extraction/services/text.py` ← `candidates/services/text_extraction.py`
- Create: `data_extraction/services/filename.py` ← `candidates/services/filename_parser.py`
- Create: `data_extraction/services/validation.py` ← `candidates/services/validation.py`
- Create: `tests/test_de_text.py` (새 import 경로 전용)
- Create: `tests/test_de_filename.py`
- Create: `tests/test_de_validation.py`

**Steps:**

- [ ] Step 1: `text.py` 작성 — `extract_text()`, `preprocess_resume_text()`, `_has_substantive_text()` 포함
- [ ] Step 2: `filename.py` 작성 — `group_by_person()` 포함
- [ ] Step 3: `validation.py` 작성 — `validate_extraction()` 포함
- [ ] Step 4: 테스트 작성 — `data_extraction.services.text` 등 새 경로에서 임포트. 기존 테스트의 assertion을 새 경로용으로 복사
- [ ] Step 5: 테스트 실행 — 새 테스트 + 기존 테스트 둘 다 통과 확인
- [ ] Step 6: 커밋

---

### Task 3: Drive 연동

**Files:**
- Create: `data_extraction/services/drive.py` ← `candidates/services/drive_sync.py`
- Create: `tests/test_de_drive.py`

**Steps:**

- [ ] Step 1: `drive.py` 작성 — `get_drive_service()`, `discover_folders()`, `list_all_files_parallel()`, `list_files_in_folder()`, `download_file()`, `parse_drive_id()` 포함
- [ ] Step 2: `CATEGORY_FOLDERS` 하드코딩 미포함. `discover_folders()`로 동적 탐색
- [ ] Step 3: 테스트 작성 — `data_extraction.services.drive` 경로 전용
- [ ] Step 4: 테스트 실행
- [ ] Step 5: 커밋

---

### Task 4: 필드 필터

**Files:**
- Create: `data_extraction/services/filters.py` ← `candidates/services/extraction_filters.py`
- Create: `tests/test_de_filters.py`

**주의:** `filters.py`는 `candidates.services.candidate_identity.select_primary_phone()`을 임포트. `candidate_identity.py`는 `candidates`에 잔류하므로 정방향 의존 (`data_extraction` → `candidates`).

**Steps:**

- [ ] Step 1: `filters.py` 작성 — `apply_regex_field_filters()` 포함. `from candidates.services.candidate_identity import select_primary_phone`
- [ ] Step 2: 테스트 작성 — `data_extraction.services.filters` 경로 전용
- [ ] Step 3: 테스트 실행
- [ ] Step 4: 커밋

---

### Task 5: LLM 추출 모듈 (실시간)

**Files:**
- Create: `data_extraction/services/extraction/__init__.py`
- Create: `data_extraction/services/extraction/prompts.py` ← 프롬프트 통합
- Create: `data_extraction/services/extraction/gemini.py` ← `candidates/services/gemini_extraction.py`
- Create: `data_extraction/services/extraction/integrity.py` ← `candidates/services/integrity/pipeline.py` + `step1_extract.py` + `step2_normalize.py` + `step3_*.py`
- Create: `data_extraction/services/extraction/validators.py` ← `candidates/services/integrity/validators.py`
- Create: `tests/test_de_extraction.py`

**Steps:**

- [ ] Step 1: `prompts.py` 작성 — 추출 시스템 프롬프트, 유저 프롬프트 빌더, 무결성 파이프라인 프롬프트 (Step 1, 2) 통합
- [ ] Step 2: `gemini.py` 작성 — `extract_candidate_data()`, `_call_gemini()` 포함. `prompts.py`에서 프롬프트 임포트
- [ ] Step 3: `validators.py` 작성 — `validate_step1()`, `validate_step2()` 포함
- [ ] Step 4: `integrity.py` 작성 — `run_integrity_pipeline()` 포함. Step 1 (extract), Step 2 (normalize career+education 병렬), Step 3 (overlap, cross-version) 통합
- [ ] Step 5: 테스트 작성 — 기존 integrity 테스트 기반, 새 import 경로 전용
- [ ] Step 6: 테스트 실행
- [ ] Step 7: 커밋

---

### Task 6: DB 저장 모듈

**Files:**
- Create: `data_extraction/services/save.py` ← `candidates/services/integrity/save.py`
- Create: `tests/test_de_save.py`

**주의:** `save.py`는 `candidates`에 잔류하는 도메인 서비스를 임포트:
- `from candidates.services.candidate_identity import select_primary_phone, build_candidate_comparison_context`
- `from candidates.services.discrepancy import compute_integrity_score, scan_candidate_discrepancies`
- `from candidates.services.detail_normalizers import normalize_awards, ...`
- `from candidates.services.salary_parser import normalize_salary`

**Steps:**

- [ ] Step 1: `save.py` 작성 — `save_pipeline_result()`, `_create_candidate()`, `_update_candidate()`, `_rebuild_sub_records()` 포함. 도메인 서비스는 `candidates.services.*`에서 임포트
- [ ] Step 2: 테스트 작성 — `data_extraction.services.save` 경로 전용, `test_save_update_path.py` 기반
- [ ] Step 3: 테스트 실행
- [ ] Step 4: 커밋

---

### Task 7: 실시간 파이프라인 오케스트레이터

**Files:**
- Create: `data_extraction/services/pipeline.py` ← `candidates/services/retry_pipeline.py`
- Create: `tests/test_de_pipeline.py`

**설계:**

```python
def run_realtime_pipeline(
    raw_text: str,
    file_path: str,
    category: str,
    filename_meta: dict,
    *,
    file_reference_date: str | None = None,
    use_integrity: bool = False,
) -> dict:
    """단건 실시간 추출 파이프라인.

    Returns:
        {"extracted": dict|None, "diagnosis": dict, "raw_text_used": str, ...}
    """
```

**Steps:**

- [ ] Step 1: `pipeline.py` 작성 — `run_realtime_pipeline()` 포함. 내부에서 `extraction/gemini.py`, `filters.py`, `validation.py` 사용
- [ ] Step 2: 테스트 작성 — `test_retry_pipeline.py` 기반, 새 import 경로 전용
- [ ] Step 3: 테스트 실행
- [ ] Step 4: 커밋

---

### Task 8: 배치 파이프라인 모듈

**Files:**
- Create: `data_extraction/services/batch/__init__.py`
- Create: `data_extraction/services/batch/artifacts.py` ← `batch_extract/services/artifacts.py`
- Create: `data_extraction/services/batch/request_builder.py` ← `batch_extract/services/request_builder.py`
- Create: `data_extraction/services/batch/api.py` ← `batch_extract/services/gemini_batch.py`
- Create: `data_extraction/services/batch/prepare.py` ← `batch_extract/services/prepare.py`
- Create: `data_extraction/services/batch/ingest.py` ← `batch_extract/services/ingest.py`
- Create: `tests/test_de_batch.py`

**주의:** `request_builder.py`는 기존 `batch_extract/services/request_builder.py`에서 이식. `build_request_line()`과 `extract_text_response()`를 포함. 프롬프트는 `extraction/prompts.py`에서 임포트.

**Steps:**

- [ ] Step 1: `artifacts.py` 작성 — 경로를 `.data_extraction/`으로 변경
- [ ] Step 2: `request_builder.py` 작성 — `build_request_line()`, `extract_text_response()` 포함. `from data_extraction.services.extraction.prompts import ...`
- [ ] Step 3: `api.py` 작성 — Gemini Batch API 연동 (upload, submit, poll, download). 공존 기간이므로 `from batch_extract.models import GeminiBatchJob` (Task 11에서 경로 전환)
- [ ] Step 4: `prepare.py` 작성 — 새 `drive.py`, `text.py`, `filename.py`, `request_builder.py` 사용
- [ ] Step 5: `ingest.py` 작성 — 새 `filters.py`, `validation.py`, `save.py`, `request_builder.py` 사용
- [ ] Step 6: 테스트 작성 — `test_batch_extract_services.py` 기반, 새 import 경로 전용
- [ ] Step 7: 테스트 실행
- [ ] Step 8: 커밋

---

### Task 9: 통합 CLI 커맨드

**Files:**
- Create: `data_extraction/management/__init__.py`
- Create: `data_extraction/management/commands/__init__.py`
- Create: `data_extraction/management/commands/extract.py`

**인터페이스:**

```bash
# 실시간 모드 (기본)
uv run python manage.py extract --drive "URL" [--folder NAME] [--workers N] [--integrity] [--limit N] [--dry-run]

# 배치 모드 — 전체 파이프라인
uv run python manage.py extract --drive "URL" --batch

# 배치 모드 — 단계별 실행
uv run python manage.py extract --drive "URL" --batch --step prepare
uv run python manage.py extract --batch --step submit --job-id 3
uv run python manage.py extract --batch --step poll --job-id 3
uv run python manage.py extract --batch --step ingest --job-id 3

# 배치 상태 확인
uv run python manage.py extract --batch --status [--job-id N]
```

**Steps:**

- [ ] Step 1: `extract.py` 커맨드 작성 — 인자: `--drive`, `--folder`, `--workers`, `--integrity`, `--limit`, `--dry-run`, `--batch`, `--step`, `--job-id`, `--status`
- [ ] Step 2: 실시간 모드 구현 — Phase 1~4 (탐색→목록→필터→처리) 병렬 파이프라인
- [ ] Step 3: 배치 모드 구현 — `--batch` 플래그로 prepare→submit→poll→ingest. `--step` + `--job-id`로 단계별 실행
- [ ] Step 4: `--status` 구현 — `GeminiBatchJob` 목록/상세 출력
- [ ] Step 5: 단계별 시간 측정 로그 포함
- [ ] Step 6: 테스트 — `--dry-run`으로 CLI 동작 확인
- [ ] Step 7: 커밋

---

### Task 10: E2E 통합 테스트

**Files:**
- Create: `tests/test_de_e2e.py`

**Steps:**

- [ ] Step 1: 실시간 모드 E2E 테스트 — Drive에서 파일 10개 다운로드 → 추출 → DB 저장 확인
- [ ] Step 2: 새 import 경로 전체 테스트 실행 (`uv run pytest tests/test_de_*.py -v`)
- [ ] Step 3: 기존 테스트 전체 실행 (`uv run pytest -v`) — 기존 테스트 깨지지 않는지 확인
- [ ] Step 4: 성능 비교 — 기존 `import_resumes` vs 새 `extract` 동일 파일 처리 시간 측정
- [ ] Step 5: 커밋

---

### Task 11: 정리 (테스트 통과 후 별도 작업)

> 이 작업은 Task 10까지 전부 통과한 후에만 진행. 별도 브랜치에서 작업 권장.

**Steps:**

- [ ] Step 1: `main/settings.py` — `INSTALLED_APPS`에서 `batch_extract` 제거
- [ ] Step 2: `batch_extract/` 디렉토리 삭제
- [ ] Step 3: `candidates/services/`에서 추출 전용 파일 삭제:
  - `drive_sync.py`, `text_extraction.py`, `filename_parser.py`
  - `extraction_filters.py`
  - `gemini_extraction.py`, `llm_extraction.py`
  - `retry_pipeline.py`, `validation.py`
  - `integrity/` 디렉토리 전체
- [ ] Step 4: `candidates/services/`에 **남겨야 하는 파일** 확인:
  - `candidate_identity.py` — `Candidate.save()`에서 사용
  - `discrepancy.py` — `scan_discrepancies` 커맨드에서 사용
  - `detail_normalizers.py` — `backfill_candidate_details`에서 사용
  - `salary_parser.py` — `backfill_candidate_details`에서 사용
  - `search.py`, `embedding.py`, `whisper.py` — UI 기능
- [ ] Step 5: `candidates/management/commands/`에서 `import_resumes.py`, `compare_extraction.py` 삭제
- [ ] Step 6: 삭제된 모듈을 임포트하는 기존 테스트 파일 삭제:
  - `tests/test_batch_extract_services.py` — `batch_extract.*` 임포트
  - `tests/test_validation.py` — `candidates.services.validation` 임포트
  - `tests/test_llm_extraction.py` — `candidates.services.llm_extraction` 임포트
  - `tests/test_drive_sync.py` — `candidates.services.drive_sync` 임포트
  - `tests/test_text_extraction.py` — `candidates.services.text_extraction` 임포트
  - `tests/test_filename_parser.py` — `candidates.services.filename_parser` 임포트
  - `tests/test_extraction_filters.py` — `candidates.services.extraction_filters` 임포트
  - `tests/test_retry_pipeline.py` — `candidates.services.retry_pipeline` 임포트
  - `tests/test_integrity_*.py` — `candidates.services.integrity.*` 임포트
  - `tests/test_import_pipeline.py` — `candidates.management.commands.import_resumes` 사용
  - `tests/test_save_update_path.py` — `candidates.services.integrity.save` 임포트
  - 각 파일에 대응하는 `tests/test_de_*` 테스트가 이미 존재하는지 확인 후 삭제
- [ ] Step 7: `data_extraction/services/save.py`의 임포트 경로가 잔류 파일을 정상 참조하는지 확인
- [ ] Step 8: 마이그레이션 squash — `data_extraction/migrations/`를 squash해서 실제 `CreateModel`이 포함된 `0001_initial.py`로 교체. `batch_extract` 마이그레이션 체인 없이도 fresh DB에서 테이블 생성 가능하게
- [ ] Step 9: `manage.py migrate --prune` — `django_migrations`에서 `batch_extract` 항목 정리
- [ ] Step 10: 전체 테스트 재실행 (`uv run pytest -v`)
- [ ] Step 11: 커밋

---

## 위험 요소 및 대응

| 위험 | 대응 |
|------|------|
| 배치 모델 런타임 충돌 | 공존 기간(Task 1~10): `data_extraction`에 배치 모델을 만들지 않음. `batch_extract.models`를 직접 임포트. Task 11에서 `batch_extract` 삭제 시 모델 이전 + `SeparateDatabaseAndState` + 실제 `CreateModel` 마이그레이션 |
| fresh DB 테이블 미생성 | Task 11의 Phase II에서 마이그레이션에 실제 `CreateModel` 포함. fresh DB에서도 테이블 생성 보장 |
| `candidate_identity` 역의존 | `candidates`에 잔류. `data_extraction`이 `candidates.services.*`를 임포트 (정방향) |
| `request_builder.py` 누락 | Task 8에 명시적으로 포함. `build_request_line()`, `extract_text_response()` 이식 |
| `--step submit` 시 어떤 job인지 모호 | `--job-id` 필수 인자. prepare 시 job ID 출력. `--status`로 목록 확인 |
| 기존 테스트와 새 테스트 시점 | **Task 10 이전:** 기존 테스트(`candidates.*`, `batch_extract.*` 임포트)와 새 테스트(`test_de_*`, `data_extraction.*` 임포트) 모두 통과해야 함. **Task 11 이후:** 기존 테스트 중 삭제된 모듈을 임포트하는 파일 제거. `test_de_*` 테스트만 남음 |
| Drive API 스레드 안전성 | 각 worker가 `get_drive_service()`로 독립 인스턴스 생성 (기존 패턴 유지) |
| LLM 비용 폭증 | `--limit`, `--dry-run` 옵션. 배치 모드는 50% 할인 |

---

## 완료 기준

### Task 10 완료 시점 (공존 기간)

1. `uv run python manage.py extract --drive "URL" --dry-run` — 20개 폴더 탐색, 파일 목록, 필터링 2초 이내
2. `uv run python manage.py extract --drive "URL" --folder Quality --integrity` — 10개 파일 추출+저장 성공
3. `uv run python manage.py extract --drive "URL" --batch --step prepare` — JSONL 파일 생성 성공
4. `uv run pytest tests/test_de_*.py -v` — 새 import 경로 전용 테스트 전체 통과
5. `uv run pytest -v` — 기존 테스트(`candidates.*`, `batch_extract.*`)도 전부 통과
6. 기존 `import_resumes`, `batch_extract` 코드에 변경 없음

### Task 11 완료 시점 (정리 후)

7. `batch_extract/` 디렉토리 삭제됨
8. 삭제된 모듈을 임포트하던 기존 테스트 파일 제거됨
9. `uv run pytest -v` — `test_de_*` 테스트 + 잔류 테스트만으로 전체 통과
10. fresh DB에서 `manage.py migrate` → `manage.py check` 정상 동작
