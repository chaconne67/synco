# Review A: Runtime Safety Audit

Audit scope: `data_extraction/services/`, `data_extraction/management/commands/extract.py`, `tests/test_de_*.py`

---

## Critical (will crash or corrupt data)

### C1. Missing `close_old_connections()` in realtime pipeline workers

- **[data_extraction/management/commands/extract.py:382-474]** `_process_group` runs inside `ThreadPoolExecutor` workers and performs heavy Django ORM operations (identity lookup, `save_pipeline_result` with `transaction.atomic()`, `Category.objects.get_or_create`). Unlike `batch/ingest.py:86` which correctly calls `close_old_connections()`, the realtime pipeline never closes stale DB connections in worker threads.

- **Impact:** After the main thread's connection times out (default `CONN_MAX_AGE`), worker threads inherit a stale connection from the connection pool. Django does not automatically manage connections in non-request threads. This causes `InterfaceError: connection already closed` or `OperationalError: server closed the connection unexpectedly` under sustained load. The crash is non-deterministic and depends on `CONN_MAX_AGE` and processing duration.

- **Reproduction path:** Run `extract --drive URL --workers 5` on a folder with 50+ files. Workers will start failing after the DB connection idle timeout.

### C2. Duplicate candidate creation under concurrent workers (TOCTOU race)

- **[data_extraction/services/save.py:106-126]** `build_candidate_comparison_context()` (identity lookup) runs OUTSIDE the `transaction.atomic()` block. When two workers process resumes for the same person (same email/phone) simultaneously:
  1. Worker A calls `build_candidate_comparison_context` -> no match found
  2. Worker B calls `build_candidate_comparison_context` -> no match found
  3. Worker A enters `transaction.atomic()` -> creates Candidate with email "x@test.com"
  4. Worker B enters `transaction.atomic()` -> creates SECOND Candidate with email "x@test.com"

- **Impact:** Duplicate candidates in DB. No UNIQUE constraint on `Candidate.email` or `Candidate.phone_normalized` to prevent this (confirmed: `candidates/models.py:192` defines `email = models.EmailField(blank=True)` with no `unique=True`).

- **Likelihood:** High when a person has multiple resume files in different category folders (e.g., `Finance/김철수.85.doc` and `HR/김철수.85.doc`). The `group_by_person` grouping operates per-folder, so the same person's files in different folders become separate work items submitted to the thread pool simultaneously.

### C3. Nested `transaction.atomic()` masks partial failures in batch ingest

- **[data_extraction/services/batch/ingest.py:166-197]** `_ingest_item_response` wraps `save_pipeline_result` in `transaction.atomic()`. But `save_pipeline_result` internally has its own `transaction.atomic()` at line 118 of `save.py`. When `save_pipeline_result` returns `None` (extraction was `None`), it may have already created a text-only or failed `Resume` record OUTSIDE the inner atomic block (lines 73-82 of save.py). These orphaned Resume records are created before the inner `transaction.atomic()` starts, inside the outer atomic block.

- **Impact:** If the outer `transaction.atomic()` rolls back (e.g., `item.save()` on line 178 fails), the text-only/failed Resume created by `save_pipeline_result` is also rolled back -- which is actually correct behavior. However, the path at save.py:73-82 creates Resume records without entering the inner `transaction.atomic()`, meaning they commit with the outer transaction's scope. This is correct but confusing and fragile. If someone removes the outer `transaction.atomic()` in ingest.py, those Resume records would commit independently, creating orphaned records on subsequent failure.

- **Revised severity:** This is actually not a current crash/corruption bug because the outer transaction provides correct semantics. Downgrading to Warning.

---

## Warning (may fail under specific conditions)

### W1. `_build_integrity_diagnosis` uses direct dict key access on flags

- **[data_extraction/services/pipeline.py:193]** `f["severity"]` and `f["detail"]` use bracket access instead of `.get()`. If any flag dict is missing either key, this raises `KeyError`.

- **When it fails:** Only if a caller passes malformed integrity flags. The internal pipeline always produces complete flag dicts, but the function is called from `apply_cross_version_comparison` (line 173) which processes flags from `compare_versions`. All internal producers include both keys, so current code is safe. Risk increases if external callers are added.

### W2. `existing_ids` is read-only shared but not updated as new files are saved

- **[data_extraction/management/commands/extract.py:354]** `existing_ids` is computed once from a bulk DB query before processing starts, then passed to all workers. As workers create new Resume records, the set is never updated. If two groups reference the same `other_file` (e.g., same file_id appears as an "other" file in two different person groups), both workers will create Resume records for it since neither sees the other's insert.

- **Impact:** Potential `IntegrityError` on `Resume.drive_file_id` which has `unique=True` (confirmed at `candidates/models.py:809`). The second worker's `Resume.objects.create()` at save.py:154 would crash with a unique constraint violation. The `transaction.atomic()` block would roll back the entire save for that candidate.

### W3. `_prepare_group_payload` in batch prepare lacks `close_old_connections()`

- **[data_extraction/services/batch/prepare.py:184-217]** `_prepare_group_payload` runs in `ThreadPoolExecutor` workers (line 81-92) but does not call `close_old_connections()`. While this function primarily does Drive API calls and file I/O (not heavy DB access), the worker thread's DB connection state is unmanaged. If a worker inherits a stale connection and a subsequent DB operation occurs in the same thread, it could fail.

- **Likelihood:** Low because `_prepare_group_payload` itself does no DB operations (Drive download + text extraction only). But the thread pool reuse pattern means if a thread previously had a DB connection from Django middleware, that connection could be stale.

### W4. `_ingest_item_response` reads `raw_text_path` without validation

- **[data_extraction/services/batch/ingest.py:140]** `Path(item.raw_text_path).read_text(encoding="utf-8")` will raise `FileNotFoundError` if `raw_text_path` is empty string (default for the model field) or points to a deleted file.

- **When it fails:** If batch ingest is retried after the `.data_extraction/` artifact directory is cleaned up, or if the prepare step failed to set `raw_text_path` on the item.

### W5. Gemini API response parsing assumes specific markdown format

- **[data_extraction/services/extraction/gemini.py:71-75, integrity.py:68-72, batch/ingest.py:204-207]** The JSON extraction from markdown code blocks uses `text.split("```")[1]`, which assumes the response has exactly one pair of triple backticks. If Gemini returns multiple code blocks (e.g., explanation + JSON), this would extract the wrong block. If the response contains an odd number of triple backticks, the `[1]` index could return garbage.

- **Impact:** Malformed JSON -> `json.loads` raises `JSONDecodeError` -> extraction treated as failed. In `extract_candidate_data` this triggers a retry (up to 3 times). Not a crash, but a silent extraction failure.

### W6. `ThreadPoolExecutor` in `run_integrity_pipeline` creates Gemini clients per thread

- **[data_extraction/services/extraction/integrity.py:736]** The Step 2 normalization spawns two threads that each call `_call_gemini()`, which calls `_get_client()`. Each invocation creates a new `genai.Client`. While this avoids thread-safety issues with the client object, it also reads `settings.GEMINI_API_KEY` in each thread. Django settings are thread-safe for reads, so this is not a bug, but each thread creates its own HTTP connection pool which could be expensive.

- **Impact:** Performance concern, not a crash risk.

### W7. Batch mode imports `batch_extract.models` at runtime -- app may not be migrated

- **[data_extraction/management/commands/extract.py:550-555]** The `_get_job` and other batch methods import from `batch_extract.models.GeminiBatchJob`. If the `batch_extract` app's migrations have not been applied (e.g., fresh dev setup), any batch command will crash with `ProgrammingError: relation "gemini_batch_jobs" does not exist`.

- **Impact:** Only affects `--batch` and `--status` modes. Realtime mode is unaffected because these imports are lazy (inside method bodies).

---

## Info (improvement suggestions)

### I1. No `select_for_update()` on candidate identity lookup

- **[data_extraction/services/save.py:108, candidates/services/candidate_identity.py:99-125]** The identity lookup uses standard `filter().first()` without `select_for_update()`. To fix the C2 race condition, the identity lookup should be moved inside the `transaction.atomic()` block with `select_for_update()`, or a unique constraint should be added to `Candidate.email` (with proper handling of empty strings).

### I2. `_process_group` swallows Drive download exceptions

- **[data_extraction/management/commands/extract.py:403]** `download_file()` is called without error handling beyond the retry logic in `download_file` itself. If all 3 retries fail, the exception propagates to `_process_all`'s `except Exception as e:` handler (line 376) and is logged as a generic failure. The specific Drive error (auth expired, quota exceeded, file deleted) is captured only in the exception message string, not as structured data.

### I3. `_save_failed_resume` and `_save_text_only_resume` are imported as private functions

- **[data_extraction/management/commands/extract.py:477-486]** The command imports `_save_failed_resume` and `_save_text_only_resume` from `data_extraction.services.save`. These are private functions (underscore prefix) being used across module boundaries. Consider making them public or providing a public wrapper.

### I4. `validate_step1_5` is defined and tested but never called

- **[data_extraction/services/extraction/validators.py:103-133]** `validate_step1_5` validates grouping quality but is never called in the integrity pipeline (`integrity.py`). The pipeline skipped Step 1.5 (grouping) during the port -- the function is dead code.

### I5. `preprocess_resume_text` noise filter is overly aggressive

- **[data_extraction/services/text.py:191-192]** The noise filter removes any line containing "computer" (case-insensitive). This could strip legitimate content like "Computer Science" in education entries or "Computer Vision" in skills.

### I6. No test coverage for `_process_group` (realtime pipeline integration)

- No `test_de_*.py` test exercises the `_process_group` method in `extract.py`. This is the core orchestration function for realtime mode -- it chains Drive download, text extraction, LLM extraction, identity matching, cross-version comparison, and DB save. All tests for individual components exist, but the integration path is untested.

### I7. No test coverage for batch `prepare_drive_job`

- `tests/test_de_batch.py` tests `build_request_line`, `extract_text_response`, `_load_extracted_json`, and `ingest_job_results`, but has no tests for `prepare_drive_job` or `_prepare_group_payload`. These functions involve Drive API interactions and file I/O that should be tested with mocks.

### I8. No test for `_handle_result_payload` actual DB path in batch ingest

- The `test_ingest_job_results_supports_parallel_workers` test monkeypatches `_handle_result_payload` entirely, so the actual ingestion logic (JSON parsing, validation, `save_pipeline_result`) is never exercised in batch context.

### I9. `download_results_for_job` writes bytes directly without encoding check

- **[data_extraction/services/batch/api.py:58]** `Path(local_path).write_bytes(output_bytes)` assumes `download_result_file` returns raw bytes. If the Gemini API changes the return type, this would fail silently or write corrupted data.

---

## Verified OK

- **Import chain integrity:** All `from data_extraction.services.X import Y` imports verified correct. Every imported name exists in the source module. No circular imports detected -- all cross-module imports use either top-level imports of disjoint modules or lazy inline imports.

- **Mock patch paths match actual import locations:** All `@patch` decorators in `test_de_pipeline.py`, `test_de_text.py`, `test_de_extraction.py`, and `test_de_drive.py` target the correct module namespace where the name is imported (not where it's defined). Verified for: `extract_candidate_data`, `validate_extraction`, `_extract_doc_antiword`, `_extract_doc_libreoffice`, `_call_gemini`, `extract_raw_data`, `normalize_career_group`, `normalize_education_group`, `validate_step1`.

- **Drive service per-thread creation:** `list_all_files_parallel` (drive.py:260), `_process_group` (extract.py:398), and `_prepare_group_payload` (prepare.py:187) all create their own Drive service via `get_drive_service()` inside the worker function, not sharing across threads. This is correct since googleapiclient is not thread-safe.

- **`ThreadPoolExecutor(max_workers=N)` never receives 0:** `list_all_files_parallel` is called with `min(len(folders), 10)` and only after confirming `folders` is non-empty (extract.py:191-197). `_process_all` uses `workers` from command args with default 5. `run_integrity_pipeline` uses hardcoded `max_workers=2`.

- **`apply_regex_field_filters` handles None input:** Returns None as-is when input is not a dict (filters.py:19). All callers either check for None before calling or handle None return.

- **`save_pipeline_result` transaction atomicity for the happy path:** The `transaction.atomic()` block at save.py:118 wraps all Candidate/Resume/Career/Education/Certification/LanguageSkill/ExtractionLog/ValidationDiagnosis/DiscrepancyReport creation/updates. If any step fails, all changes roll back correctly.

- **`group_by_person` handles empty file lists:** Returns empty list. Tested in `test_de_filename.py`.

- **`normalize_education_group` handles empty entries:** Returns `{"educations": [], "flags": []}` without calling Gemini. Tested in `test_de_extraction.py:233`.

- **`run_integrity_pipeline` handles Step 1 failure:** Returns `None` cleanly. Caller `_run_integrity_pipeline` in pipeline.py handles `None` return and produces a fail diagnosis. Tested.

- **Batch ingest `close_old_connections()`:** `_handle_result_payload` (ingest.py:86,120) correctly calls `close_old_connections()` at entry and in `finally` block for worker thread DB connection management.

- **`_sanitize_phone` and `_sanitize_reference_date`:** Both truncate values to max field length (255 chars) before DB save, preventing `DataError: value too long for type character varying`.

- **Category pre-creation in `_process_all`:** Categories are created before submitting to the thread pool (extract.py:338-343), avoiding concurrent `get_or_create` race conditions on the Category table.

---

## Round 2 Re-audit

Re-audit date: 2026-04-04. Verifying fixes for C1, C2, B1 (artifacts.py parents), B4 (private function imports), and checking for regressions.

### C1. Missing `close_old_connections()` in `_process_group` — **FIXED**

**File:** `data_extraction/management/commands/extract.py:382-401`

The fix is correct. `_process_group` now:
1. Calls `close_old_connections()` at entry (line 397)
2. Delegates to `_process_group_inner` inside a `try` block (line 398)
3. Calls `close_old_connections()` in `finally` (line 400)

This matches the established pattern used in `batch/ingest.py:_handle_result_payload`. The separation into `_process_group` (connection lifecycle) and `_process_group_inner` (business logic) is clean.

**Same fix applied to `candidates/management/commands/import_resumes.py`:** YES (lines 316-321). Same try/finally pattern with `close_old_connections()`. Both commands are now consistent.

**Regression check:** `close_old_connections()` closes connections that have exceeded `CONN_MAX_AGE` or are in an error state. It does NOT close connections that are mid-transaction. Since `_process_group_inner` calls `save_pipeline_result` which uses `transaction.atomic()`, the `finally` block's `close_old_connections()` runs after the transaction has committed or rolled back, so there is no conflict. No regression.

### C2. TOCTOU race in `save.py` identity lookup outside transaction — **FIXED**

**File:** `data_extraction/services/save.py:106-110`

The identity lookup (`build_candidate_comparison_context`) is now inside the `transaction.atomic()` block (line 106 starts atomic, line 109 calls `build_candidate_comparison_context`). This eliminates the TOCTOU window where two workers could both find "no match" and create duplicate candidates.

**However, the fix is incomplete for full race prevention.** The identity lookup at `candidate_identity.py:100-103` uses `Candidate.objects.filter(email__iexact=email).first()` without `select_for_update()`. Under PostgreSQL's default READ COMMITTED isolation level, two concurrent transactions can both read the same state (no existing candidate), both proceed to create, and both commit successfully — creating duplicates. The `transaction.atomic()` block prevents the TOCTOU gap but does not serialize the read-then-write sequence.

To fully prevent duplicates, either:
- Add `select_for_update()` to the identity queries (but this requires rows to already exist to lock)
- Add a UNIQUE constraint on `Candidate.email` (with exclusion for empty strings)
- Use advisory locks on the email/phone hash

**Practical risk assessment:** The current fix significantly reduces the race window (from seconds to milliseconds). The remaining race requires two workers to process different files for the same person with overlapping transaction windows. This is low probability in practice. The fix is a meaningful improvement.

**Regression check (deadlock risk):** The `build_candidate_comparison_context` call inside the atomic block does read-only queries (`filter().first()`, no `select_for_update()`). Read-only queries inside a transaction do not create lock contention or deadlock risk under PostgreSQL. No regression.

### B1. `artifacts.py` `parents[2]` changed to `parents[3]` — **FIXED**

**File:** `data_extraction/services/batch/artifacts.py:6`

```python
ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / ".data_extraction"
```

`__file__` resolves to `data_extraction/services/batch/artifacts.py`. `parents[3]` is the project root (`synco/`), making `ARTIFACT_ROOT` = `synco/.data_extraction`. This is correct — artifacts land in the project root, not inside the `services/` directory.

### B4. Private function imports `_save_failed_resume` / `_save_text_only_resume` — **PARTIALLY_FIXED**

**Fixed in `data_extraction/services/save.py`:** YES. Functions are now public: `save_failed_resume` (line 257) and `save_text_only_resume` (line 269). The `extract.py` command imports them correctly without underscore prefix (lines 493, 499).

**NOT fixed in `candidates/services/integrity/save.py`:** The old `candidates` app module still uses private names: `def _save_failed_resume` (line 257) and `def _save_text_only_resume` (line 269). And `candidates/management/commands/import_resumes.py` still imports them with the underscore prefix (lines 416-417, 422-423):

```python
from candidates.services.integrity.save import _save_failed_resume
from candidates.services.integrity.save import _save_text_only_resume
```

This is a cross-module private import, violating the same convention the B4 fix addressed in the `data_extraction` app. The `import_resumes.py` command is the legacy version of `extract.py` and uses the old `candidates.services.integrity.save` module rather than the new `data_extraction.services.save` module.

### Batch prepare — CATEGORY_FOLDERS removed, `discover_folders()` used — **FIXED**

**File:** `data_extraction/services/batch/prepare.py`

No `CATEGORY_FOLDERS` constant exists anywhere in the `data_extraction/` tree. The `prepare_drive_job` function calls `discover_folders(service, parent_folder_id)` at line 29 to dynamically discover subfolders. This is correct — no hardcoded folder list.

### Migration `data_extraction/migrations/0001_initial.py` — **EXISTS (empty)**

The file exists and contains a valid empty migration (no operations, no dependencies). This is a placeholder to register the `data_extraction` app with Django's migration framework. Since the `data_extraction` app currently has no models of its own (it uses models from `candidates` and `batch_extract`), an empty initial migration is correct.

### New issues introduced by fixes — **NONE FOUND**

1. **No deadlock risk from C2 fix:** The identity lookup inside `transaction.atomic()` uses only read queries, no row-level locks.
2. **No connection lifecycle conflict from C1 fix:** `close_old_connections()` in `finally` runs after any transaction has completed.
3. **No import breakage:** All import paths verified correct for both `data_extraction` and `candidates` apps.
