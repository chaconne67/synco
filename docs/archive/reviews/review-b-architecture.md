# Review B: Architecture Consistency Audit

Audited: `data_extraction/` app implementation
Plan: `docs/plans/2026-04-04-data-extraction-app-plan.md`

---

## Plan Deviations

- **[Task 1] Missing migration file.** Plan line 215 specifies `data_extraction/migrations/0001_initial.py` (empty, for app registration). Only `__init__.py` exists in `data_extraction/migrations/`. While Django can function without it (since `models.py` defines no models), the plan explicitly calls for it and it provides a clean starting point for Phase II model migration.

- **[Task 1] Missing migration file content.** Plan line 226 says: "data_extraction/migrations/0001_initial.py는 빈 마이그레이션 (앱 등록용)". This file does not exist at all.

- **[Task 7] Function name mismatch.** Plan line 355 defines the pipeline entry point as `run_realtime_pipeline()`. The implementation at `data_extraction/services/pipeline.py:14` uses `run_extraction_with_retry()` instead. While the signature is similar, the name deviates from the plan. The plan explicitly chose `run_realtime_pipeline` to distinguish realtime from batch mode.

- **[Task 7] Signature divergence.** Plan line 355-368 defines `use_integrity: bool = False` as keyword-only. Implementation at `pipeline.py:14-22` uses `use_integrity_pipeline: bool = False` and adds an extra parameter `previous_data: dict | None = None` not in the plan. Also `file_reference_date` is positional in the implementation but keyword-only in the plan.

- **[Task 8] CATEGORY_FOLDERS hardcoded in batch/prepare.py.** Plan line 114 says `drive.py` should remove `CATEGORY_FOLDERS`. While `drive.py` correctly omits it, `batch/prepare.py:19-40` reintroduces the same hardcoded list of 20 category folder names. The plan's intent was to use `discover_folders()` for dynamic traversal everywhere. The realtime CLI correctly uses `discover_folders()`, but the batch prepare path does not.

- **[Task 8] Artifact path miscalculation.** `data_extraction/services/batch/artifacts.py:6` sets `ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / ".data_extraction"`. Because the file is 3 levels deep (`data_extraction/services/batch/artifacts.py`), `parents[2]` resolves to `/home/work/synco/data_extraction/`, making artifacts go to `data_extraction/.data_extraction/` (inside the app). The plan (line 129) says "경로를 `.data_extraction/`으로 변경", implying project root level. Should be `parents[3]` to get `/home/work/synco/.data_extraction/`.

- **[Task 9] Status display count.** Plan line 180 says `--status` without `--job-id` shows "최근 10개". Implementation at `extract.py:738` uses `[:20]` (latest 20).

- **[Task 10] Missing E2E test.** Plan line 447 specifies `tests/test_de_e2e.py`. This file does not exist. Nine `test_de_*.py` files exist (text, filename, validation, filters, drive, save, extraction, pipeline, batch) but not the E2E test.

---

## Dependency Violations

No violations found. No file in `candidates/` imports from `data_extraction`.

`data_extraction` imports from `candidates` are limited to the allowed domain services:
- `candidates.services.candidate_identity` -- `select_primary_phone`, `build_candidate_comparison_context` (filters.py:6, save.py:37,106, extract.py:439)
- `candidates.services.discrepancy` -- `compute_integrity_score`, `scan_candidate_discrepancies`, `_build_summary` (save.py:22-26)
- `candidates.services.detail_normalizers` -- normalization functions (save.py:298,423)
- `candidates.services.salary_parser` -- `normalize_salary` (save.py:308,433)
- `candidates.models` -- domain models (save.py:10-20, extract.py:39)
- `batch_extract.models` -- batch models during coexistence (api.py:10, prepare.py:6, ingest.py:10, extract.py:550,558,730)

**Minor concern:** `save.py:25` imports `_build_summary` (a private function by Python convention) from `candidates.services.discrepancy`. This creates a coupling to an internal implementation detail. Should be made public in the source module or wrapped.

---

## API Mismatches

- **[pipeline.py] `run_realtime_pipeline()` -> `run_extraction_with_retry()`** -- Function renamed. Plan specifies `run_realtime_pipeline` (line 355). The original source `candidates/services/retry_pipeline.py` also uses `run_extraction_with_retry`, so the implementation preserved the original name rather than adopting the plan's new name. The plan explicitly chose a new name for clarity.

All other public function names match between originals and ported versions:

| Module | Functions | Match |
|--------|-----------|-------|
| text.py | `extract_text`, `preprocess_resume_text`, `extract_text_libreoffice` | OK |
| filename.py | `parse_filename`, `group_by_person` | OK |
| validation.py | `validate_rules`, `validate_cross_check`, `compute_overall_confidence`, `validate_extraction` | OK |
| filters.py | `apply_regex_field_filters` | OK |
| extraction/gemini.py | `extract_candidate_data` | OK |
| extraction/prompts.py | `build_extraction_prompt`, `build_step1_prompt` + constants | OK |
| extraction/integrity.py | `run_integrity_pipeline`, `compare_versions` + internals | OK |
| extraction/validators.py | `validate_step1`, `validate_step1_5`, `validate_step2` | OK |
| save.py | `save_pipeline_result` | OK |
| batch/artifacts.py | `ensure_job_dirs`, `request_file_path`, `result_file_path`, `raw_text_path` | OK |
| batch/request_builder.py | `build_request_line`, `extract_text_response` | OK |
| batch/api.py | `get_client`, `upload_request_file`, `create_batch_job`, `get_batch_job`, `download_result_file`, `download_results_for_job`, `sync_job_from_remote` | OK |
| batch/prepare.py | `prepare_drive_job` | OK |
| batch/ingest.py | `ingest_job_results` | OK |
| drive.py | `get_drive_service`, `discover_folders`, `list_all_files_parallel`, `list_files_in_folder`, `download_file`, `parse_drive_id`, `find_category_folder`, `list_root_folders` | OK (2 extra functions, acceptable) |

---

## CLI Issues

- All 10 planned arguments are present and correctly implemented: `--drive`, `--folder`, `--workers`, `--integrity`, `--limit`, `--dry-run`, `--batch`, `--step`, `--job-id`, `--status`.

- **`--status` shows 20 instead of 10.** `extract.py:738` uses `[:20]`. Plan line 180 says "최근 10개".

- **Private function imports from save.py.** `extract.py:477` imports `_save_failed_resume` and `extract.py:484` imports `_save_text_only_resume`. These are private functions (underscore prefix) being used as a public API across module boundaries. They should either be renamed without the underscore prefix or wrapped in a public function.

---

## Batch Model Coexistence

- `data_extraction/models.py` contains no model classes -- correct per Phase I plan.
- All batch-related code imports from `batch_extract.models` -- correct per Phase I plan.
- Verified locations: `api.py:10`, `prepare.py:6`, `ingest.py:10`, `extract.py:550,558,730`.

---

## Naming and Module Boundaries

- **`CATEGORY_FOLDERS` in wrong module.** `batch/prepare.py:19-40` contains a hardcoded 20-item category folder list. This was supposed to be eliminated by `discover_folders()`. If batch mode still needs a default list, it belongs in a shared config, not hardcoded in the prepare module.

- **`_save_failed_resume` / `_save_text_only_resume` scope.** These functions in `save.py` are prefixed with `_` (private) but are imported by `extract.py`. Either make them public or move the logic into the CLI command.

- **Module boundaries are otherwise clean.** The 4-phase pipeline (collect -> extract -> validate -> save) is properly separated across modules. Internal cross-references within `data_extraction` use the correct import paths.

---

## Test Naming Convention

- All 9 test files follow the `test_de_*.py` pattern: `test_de_text.py`, `test_de_filename.py`, `test_de_validation.py`, `test_de_filters.py`, `test_de_drive.py`, `test_de_save.py`, `test_de_extraction.py`, `test_de_pipeline.py`, `test_de_batch.py`.
- All test imports use `data_extraction.services.*` paths -- no `candidates.services.*` imports found in test files.
- `test_de_e2e.py` is missing (planned in Task 10).

---

## Verified OK

- `data_extraction` registered in `main/settings.py` INSTALLED_APPS (line 56)
- `DataExtractionConfig` in `apps.py` with correct `name` and `verbose_name`
- No dependency violations: `candidates/` has zero imports from `data_extraction`
- `data_extraction/models.py` is model-free (Phase I coexistence correct)
- All batch model references go to `batch_extract.models`
- `drive.py` removed `CATEGORY_FOLDERS` (plan line 114) -- present only in batch/prepare.py
- All 10 CLI arguments present and functional
- CLI `--step` choices match plan: `prepare`, `submit`, `poll`, `ingest`
- `--job-id` validation: required for `submit|poll|ingest`, not required for `prepare`
- `--drive` validation: required for realtime mode and `--step prepare`
- Phase timing logs included in realtime mode output
- `__init__.py` files present in all package directories
- 9 of 10 planned test files created with correct naming convention
- All test files import from `data_extraction.services.*` (not `candidates.services.*`)
- Prompts consolidated into `extraction/prompts.py` from multiple original sources
- Integrity pipeline consolidated from 5 original files into single `extraction/integrity.py`
- Validators ported unchanged from `candidates/services/integrity/validators.py`
- `artifacts.py` uses `.data_extraction/` prefix (though path calculation is wrong -- see Plan Deviations)

---

## Round 2 Re-audit

Re-audit date: 2026-04-04
Scope: verify fixes to 5 issues reported in Round 1.

### 1. Artifact path miscalculation (parents[2] → parents[3]) — **FIXED**

`data_extraction/services/batch/artifacts.py:6` now reads:

```python
ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / ".data_extraction"
```

Verified: `parents[3]` from `data_extraction/services/batch/artifacts.py` resolves to `/home/work/synco/` (project root). Artifacts land at `/home/work/synco/.data_extraction/` as intended by the plan.

### 2. CATEGORY_FOLDERS hardcoded in batch/prepare.py — **FIXED**

`data_extraction/services/batch/prepare.py` no longer contains any `CATEGORY_FOLDERS` constant. Grep for `CATEGORY_FOLDERS` across `data_extraction/` returns zero matches.

The module now imports `discover_folders` from `data_extraction.services.drive` (line 11) and calls `discover_folders(service, parent_folder_id)` at line 29 to dynamically enumerate subfolders. The optional `folder_name` parameter filters the discovered list when a single subfolder is requested (line 32). This matches the plan's intent for dynamic traversal.

No new issues introduced -- the import path and call signature are correct.

### 3. Missing 0001_initial.py migration — **FIXED**

`data_extraction/migrations/0001_initial.py` exists and contains a valid empty migration:

```python
class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = []
```

This satisfies the plan requirement for an app-registration migration with no models (Phase I).

### 4. _save_failed_resume / _save_text_only_resume private function imports — **FIXED**

`data_extraction/services/save.py` now exposes these as public functions (no underscore prefix):
- `save_failed_resume()` at line 257
- `save_text_only_resume()` at line 269

`data_extraction/management/commands/extract.py` imports them correctly:
- Line 492: `from data_extraction.services.save import save_failed_resume`
- Line 499: `from data_extraction.services.save import save_text_only_resume`

The CLI command wraps these in thin methods (`_save_failed_resume`, `_save_text_only_resume` on the Command class) for local call convenience, which is fine -- the cross-module boundary now uses the public names.

Internal references within `save.py` (lines 74, 81 in `save_pipeline_result()`) also call the public names directly. No underscore-prefixed versions remain.

### 5. extract.py uses public names — **FIXED**

Confirmed in conjunction with item 4 above. `extract.py` no longer imports any underscore-prefixed functions from `save.py`. All three save-related imports (`save_pipeline_result`, `save_failed_resume`, `save_text_only_resume`) use the public API.

### New issues introduced by fixes

**None found.** Specifically checked:
- `prepare.py` import of `discover_folders` resolves correctly via `data_extraction.services.drive`
- `discover_folders()` signature (`service, parent_id: str`) matches the call site in `prepare.py`
- `save.py` public API is coherent: `save_pipeline_result`, `save_failed_resume`, `save_text_only_resume`
- No circular imports introduced
- No stale references to old private names remain anywhere in `data_extraction/`

### Previously noted items (unchanged, not re-audited)

- `run_extraction_with_retry` name kept for backward compat (intentional, not a bug)
- `--status` shows 20 instead of 10 (minor, cosmetic)
- `test_de_e2e.py` still missing (separate future work)
- `_build_summary` private import from `candidates.services.discrepancy` still present (pre-existing, not part of this fix batch)
