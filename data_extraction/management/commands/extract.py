"""Unified extraction command: realtime and batch modes.

Usage:
    # Realtime mode (default) — Google Drive URL or folder ID
    uv run python manage.py extract --drive "URL_OR_ID"

    # Process a single subfolder
    uv run python manage.py extract --drive "URL_OR_ID" --folder HR

    # Control parallelism, use integrity pipeline
    uv run python manage.py extract --drive "URL_OR_ID" --workers 3 --integrity

    # Dry run — list files without processing
    uv run python manage.py extract --drive "URL_OR_ID" --dry-run

    # Batch mode — full pipeline
    uv run python manage.py extract --drive "URL_OR_ID" --batch

    # Batch mode — step by step
    uv run python manage.py extract --drive "URL_OR_ID" --batch --step prepare
    uv run python manage.py extract --batch --step submit --job-id JOB_UUID
    uv run python manage.py extract --batch --step poll --job-id JOB_UUID
    uv run python manage.py extract --batch --step ingest --job-id JOB_UUID
    uv run python manage.py extract --batch --step next --job-id JOB_UUID

    # Status
    uv run python manage.py extract --batch --status
    uv run python manage.py extract --batch --status --job-id JOB_UUID
"""

from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError

from candidates.models import Category, Resume
from data_extraction.models import ResumeExtractionState
from data_extraction.services.drive import (
    discover_folders,
    download_file,
    get_drive_service,
    list_all_files_parallel,
    parse_drive_id,
)
from data_extraction.services.filename import group_by_person
from data_extraction.services.pipeline import run_extraction_with_retry
from data_extraction.services.state import (
    ensure_resume_for_drive_file,
    mark_attempt_started,
    mark_downloaded,
    mark_extracting,
    mark_text_extracted,
)
from data_extraction.services.text import extract_text, preprocess_resume_text


class Command(BaseCommand):
    help = (
        "Unified extraction CLI: download resumes from Google Drive, "
        "extract text, LLM parse, and save to DB (realtime or batch mode)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--drive",
            type=str,
            help="Google Drive folder URL or ID (subfolders are auto-discovered)",
        )
        parser.add_argument(
            "--folder",
            type=str,
            help="Process only this subfolder name (e.g., 'HR')",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=5,
            help="Parallel workers for processing (default: 5)",
        )
        parser.add_argument(
            "--integrity",
            action="store_true",
            help="Use integrity pipeline (Step 1->2->3) instead of legacy extraction",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max files per folder (0=unlimited)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files without processing",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-extract existing files (skip check disabled)",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Retry files whose previous extraction status is failed",
        )
        parser.add_argument(
            "--failed-only",
            action="store_true",
            help="Process only files whose previous extraction status is failed",
        )
        parser.add_argument(
            "--shuffle",
            action="store_true",
            help="Randomize file order before applying --limit",
        )
        parser.add_argument(
            "--birth-year-filter",
            action="store_true",
            help="Enable pre-LLM birth-year filtering after text extraction",
        )
        parser.add_argument(
            "--birth-year",
            type=int,
            help="4-digit birth year cutoff or 2-digit age cutoff",
        )
        parser.add_argument(
            "--batch",
            action="store_true",
            help="Use batch mode (Gemini Batch API)",
        )
        parser.add_argument(
            "--step",
            type=str,
            choices=["prepare", "submit", "poll", "ingest", "next"],
            help="Batch step: prepare, submit, poll, ingest, next",
        )
        parser.add_argument(
            "--job-id",
            type=str,
            help="Batch job ID (required for submit/poll/ingest steps)",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show batch job status",
        )
        parser.add_argument(
            "--provider",
            type=str,
            choices=["gemini", "openai"],
            default="gemini",
            help="LLM provider for extraction (default: gemini)",
        )

    def handle(self, *args, **options):
        self._validate_options(options)

        if options.get("status"):
            return self._handle_status(options)

        if options.get("batch"):
            self._handle_batch(options)
            return None

        return self._handle_realtime(options)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_options(self, options):
        step = options.get("step")
        job_id = options.get("job_id")
        drive = options.get("drive")
        batch = options.get("batch")
        status = options.get("status")
        birth_year_filter = options.get("birth_year_filter")
        birth_year = options.get("birth_year")
        provider = options.get("provider", "gemini")

        # --status doesn't require --drive
        if status:
            return

        # Batch mode runs through the Gemini Batch API; OpenAI has no equivalent
        # endpoint here. Reject the combination loudly instead of silently
        # falling back to Gemini and producing results inconsistent with what
        # `--provider openai` produces in realtime.
        if batch and provider != "gemini":
            raise CommandError(
                "--provider 'openai' is not supported with --batch (Gemini Batch API only). "
                "Use realtime mode or run with --provider gemini."
            )

        if birth_year_filter and birth_year is None:
            raise CommandError("--birth-year is required with --birth-year-filter")
        if birth_year_filter:
            from data_extraction.services.text import normalize_birth_year_filter_value

            try:
                normalize_birth_year_filter_value(birth_year)
            except ValueError as exc:
                raise CommandError(str(exc))

        # --step submit|poll|ingest|next requires --job-id
        if step in ("submit", "poll", "ingest", "next") and not job_id:
            raise CommandError(f"--step {step} requires --job-id")

        # Realtime mode and --step prepare require --drive
        if not batch and not drive:
            raise CommandError("--drive is required for realtime mode")
        if batch and step == "prepare" and not drive:
            raise CommandError("--drive is required for --step prepare")

        # Full batch (no step) requires --drive
        if batch and not step and not drive:
            raise CommandError("--drive is required for batch mode")

    # ------------------------------------------------------------------
    # Realtime mode
    # ------------------------------------------------------------------

    def _handle_realtime(self, options):
        parent_folder_id = parse_drive_id(options["drive"])
        folder_filter = options.get("folder")
        limit = options.get("limit") or 0
        dry_run = options.get("dry_run")
        workers = options.get("workers") or 5
        self.use_integrity = options.get("integrity", False)
        self.force = options.get("force", False)
        self.retry_failed = options.get("retry_failed", False)
        self.failed_only = options.get("failed_only", False)
        self.shuffle = options.get("shuffle", False)
        self.provider = options.get("provider", "gemini")
        self.birth_year_filter = options.get("birth_year_filter", False)
        self.birth_year_value = options.get("birth_year")

        provider_label = (
            f" [provider: {self.provider}]" if self.provider != "gemini" else ""
        )
        self.stdout.write(
            f"\n=== Extract {'(DRY RUN)' if dry_run else ''}{provider_label} ==="
        )

        start_time = time.time()

        # -- Phase 1: Discover folders --
        t0 = time.time()
        service = get_drive_service()
        folders = discover_folders(service, parent_folder_id)

        if folder_filter:
            folders = [f for f in folders if f["name"] == folder_filter]
            if not folders:
                self.stderr.write(
                    f"Folder '{folder_filter}' not found under {parent_folder_id}."
                )
                return

        folder_names = [f["name"] for f in folders]
        phase1_sec = time.time() - t0
        self.stdout.write(
            f"Phase 1 — Discover: {len(folders)} folders found ({phase1_sec:.1f}s)"
        )
        self.stdout.write(f"  {', '.join(folder_names)}")

        # -- Phase 2: List files in all folders (parallel) --
        if not folders:
            self.stdout.write("No folders found.")
            self._print_summary(
                {
                    "total_files": 0,
                    "total_groups": 0,
                    "skipped": 0,
                    "new_groups": [],
                    "existing_ids": set(),
                    "affected_folders": set(),
                },
                0,
                0,
                time.time() - start_time,
                phase1_sec,
            )
            return

        t0 = time.time()
        folder_files = list_all_files_parallel(folders, workers=min(len(folders), 10))
        phase2_sec = time.time() - t0

        total_files = sum(len(files) for files in folder_files.values())
        self.stdout.write(
            f"Phase 2 — File listing: {total_files} files across "
            f"{len(folder_files)} folders ({phase2_sec:.1f}s)"
        )

        # -- Phase 3: Group, filter, and collect work items --
        t0 = time.time()
        work_items = self._collect_work_items(folder_files, limit)
        phase3_sec = time.time() - t0

        self.stdout.write(
            f"Phase 3 — Filter: {work_items['total_groups']} groups, "
            f"{work_items['skipped']} existing, "
            f"{len(work_items['new_groups'])} new ({phase3_sec:.1f}s)"
        )

        if dry_run:
            self._dry_run_report(work_items["new_groups"])
            self._print_summary(
                work_items,
                0,
                0,
                time.time() - start_time,
                phase1_sec,
                phase2_sec,
                phase3_sec,
            )
            return

        if not work_items["new_groups"]:
            self.stdout.write("Nothing new to process.")
            self._print_summary(
                work_items,
                0,
                0,
                time.time() - start_time,
                phase1_sec,
                phase2_sec,
                phase3_sec,
            )
            return

        # -- Phase 4: Process all new groups in parallel --
        t0 = time.time()
        succeeded, failed, filtered = self._process_all(
            work_items["new_groups"], workers, work_items["existing_ids"]
        )
        phase4_sec = time.time() - t0

        self.stdout.write(
            f"Phase 4 — Process: {succeeded} succeeded, {failed} failed, "
            f"{filtered} filtered ({phase4_sec:.1f}s)"
        )

        # Update category candidate counts
        for folder_name in work_items["affected_folders"]:
            try:
                cat = Category.objects.get(name=folder_name)
                cat.candidate_count = cat.candidates.count()
                cat.save(update_fields=["candidate_count"])
            except Category.DoesNotExist:
                pass

        self._print_summary(
            work_items,
            succeeded,
            failed,
            time.time() - start_time,
            phase1_sec,
            phase2_sec,
            phase3_sec,
            phase4_sec,
            filtered=filtered,
        )

    def _collect_work_items(
        self,
        folder_files: dict[str, list[dict]],
        limit: int,
    ) -> dict:
        """Group files, check DB, return new work items across all folders."""
        all_new_groups: list[dict] = []
        total_groups = 0
        total_skipped = 0
        total_files = 0
        affected_folders: set[str] = set()

        # Collect all file IDs for a single bulk DB check
        all_file_ids: set[str] = set()
        folder_groups: dict[str, list[dict]] = {}

        for folder_name, files in folder_files.items():
            normalized = [
                {
                    "file_name": f["name"],
                    "file_id": f["id"],
                    "mime_type": f.get("mimeType", ""),
                    "file_size": int(f.get("size", 0)) if f.get("size") else 0,
                    "modified_time": f.get("modifiedTime", ""),
                }
                for f in files
            ]
            if getattr(self, "shuffle", False):
                import random

                random.shuffle(normalized)
            total_files += len(normalized)
            groups = group_by_person(normalized)
            folder_groups[folder_name] = groups
            total_groups += len(groups)

            for g in groups:
                all_file_ids.add(g["primary"]["file_id"])
                for other in g["others"]:
                    all_file_ids.add(other["file_id"])

        # Single bulk DB query
        resume_statuses = dict(
            Resume.objects.filter(drive_file_id__in=all_file_ids).values_list(
                "drive_file_id",
                "processing_status",
            )
        )
        existing_ids = set(resume_statuses)

        # Filter new groups
        for folder_name, groups in folder_groups.items():
            for g in groups:
                primary_id = g["primary"]["file_id"]
                is_existing = primary_id in existing_ids
                is_retryable_failed = (
                    getattr(self, "retry_failed", False)
                    or getattr(self, "failed_only", False)
                ) and resume_statuses.get(primary_id) == Resume.ProcessingStatus.FAILED
                if getattr(self, "failed_only", False) and not is_retryable_failed:
                    if is_existing:
                        total_skipped += 1
                    continue
                if (
                    is_existing
                    and not getattr(self, "force", False)
                    and not is_retryable_failed
                ):
                    total_skipped += 1
                else:
                    g["_folder_name"] = folder_name
                    all_new_groups.append(g)
                    affected_folders.add(folder_name)

        if limit:
            all_new_groups = all_new_groups[:limit]

        return {
            "new_groups": all_new_groups,
            "total_files": total_files,
            "total_groups": total_groups,
            "skipped": total_skipped,
            "existing_ids": existing_ids,
            "affected_folders": affected_folders,
        }

    def _process_all(
        self,
        groups: list[dict],
        workers: int,
        existing_ids: set,
    ) -> tuple[int, int, int]:
        """Process all groups in a single thread pool."""
        succeeded = 0
        failed = 0
        filtered = 0

        # Pre-create categories
        folder_names = {g["_folder_name"] for g in groups}
        categories = {}
        for name in folder_names:
            categories[name], _ = Category.objects.get_or_create(
                name=name,
                defaults={"name_ko": ""},
            )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for group in groups:
                folder_name = group["_folder_name"]
                future = executor.submit(
                    self._process_group,
                    group=group,
                    folder_name=folder_name,
                    category=categories[folder_name],
                    existing_ids=existing_ids,
                )
                futures[future] = group

            for future in as_completed(futures):
                group = futures[future]
                primary_name = group["primary"]["file_name"]
                folder_name = group["_folder_name"]
                try:
                    result = future.result()
                    if result == "filtered":
                        filtered += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  FILTER: [{folder_name}] {primary_name} (birth year)"
                            )
                        )
                    elif result:
                        succeeded += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  OK: [{folder_name}] {primary_name}")
                        )
                    else:
                        failed += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  SKIP: [{folder_name}] {primary_name} (extraction failed)"
                            )
                        )
                except Exception as e:
                    failed += 1
                    self.stderr.write(f"  FAIL: [{folder_name}] {primary_name}: {e}")

        return succeeded, failed, filtered

    def _process_group(
        self,
        group: dict,
        folder_name: str,
        category: Category,
        existing_ids: set,
    ) -> bool | str:
        """Process a single person group: download, extract, LLM, validate, save.

        Each worker creates its own Drive service (not thread-safe).
        Returns True if successful, False if skipped/failed.
        """
        from django.db import close_old_connections

        close_old_connections()
        try:
            return self._process_group_inner(group, folder_name, category, existing_ids)
        finally:
            close_old_connections()

    def _process_group_inner(
        self,
        group: dict,
        folder_name: str,
        category: Category,
        existing_ids: set,
    ) -> bool | str:
        primary = group["primary"]
        others = group["others"]
        parsed = group["parsed"]
        service = get_drive_service()
        resume = ensure_resume_for_drive_file(primary, folder_name)
        mark_attempt_started(
            resume,
            status=ResumeExtractionState.Status.DOWNLOADING,
            provider=self.provider,
            pipeline="integrity" if self.use_integrity else "legacy",
        )

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Step 1: Download primary file
                try:
                    dest_path = os.path.join(tmpdir, primary["file_name"])
                    download_file(service, primary["file_id"], dest_path)
                    mark_downloaded(resume)
                except Exception as e:
                    self._save_failed_resume(
                        primary,
                        folder_name,
                        f"Download failed: {e}",
                        filename_meta=parsed,
                    )
                    return False

                # Step 2: Extract text + preprocess
                try:
                    raw_text = extract_text(dest_path)
                    raw_text = preprocess_resume_text(raw_text)
                    mark_text_extracted(resume)
                except Exception as e:
                    self._save_failed_resume(
                        primary,
                        folder_name,
                        f"Text extraction failed: {e}",
                        filename_meta=parsed,
                    )
                    return False

                from data_extraction.services.text import classify_text_quality

                quality = classify_text_quality(raw_text)
                if quality != "ok":
                    self._save_failed_resume(
                        primary,
                        folder_name,
                        f"Text quality: {quality}",
                        filename_meta=parsed,
                    )
                    return False

                if self.birth_year_filter:
                    from data_extraction.services.text import passes_birth_year_filter

                    birth_filter = passes_birth_year_filter(
                        raw_text,
                        self.birth_year_value,
                        enabled=True,
                    )
                    if not birth_filter.passed:
                        from data_extraction.services.state import mark_completed

                        mark_completed(
                            resume,
                            status=ResumeExtractionState.Status.SKIPPED,
                            error=f"Birth year filter: {birth_filter.reason}",
                            provider=self.provider,
                            pipeline=("integrity" if self.use_integrity else "legacy"),
                            metadata={
                                "birth_year_filter": {
                                    "cutoff_year": birth_filter.cutoff_year,
                                    "detected_year": birth_filter.detected_year,
                                    "source": birth_filter.source,
                                    "evidence": birth_filter.evidence,
                                    "reason": birth_filter.reason,
                                }
                            },
                        )
                        return "filtered"

                # Step 3: Extract + Validate + Retry
                mark_extracting(
                    resume,
                    provider=self.provider,
                    pipeline="integrity" if self.use_integrity else "legacy",
                )
                pipeline_result = run_extraction_with_retry(
                    raw_text=raw_text,
                    file_path=dest_path,
                    category=folder_name,
                    filename_meta=parsed,
                    file_reference_date=primary.get("modified_time"),
                    use_integrity_pipeline=self.use_integrity,
                    provider=self.provider,
                )

                extracted = pipeline_result["extracted"]
                if not extracted:
                    self._save_text_only_resume(
                        primary,
                        folder_name,
                        raw_text=raw_text,
                        error_msg="Extraction failed after retries; stored raw text only",
                        filename_meta=parsed,
                    )
                    return False

                raw_text = pipeline_result["raw_text_used"]

                if not extracted.get("name"):
                    extracted["name"] = parsed.get("name") or primary["file_name"]

                comparison_context = None
                if extracted:
                    from candidates.services.candidate_identity import (
                        build_candidate_comparison_context,
                    )

                    comparison_context = build_candidate_comparison_context(extracted)
                    if (
                        self.use_integrity
                        and comparison_context
                        and comparison_context.previous_data
                    ):
                        from data_extraction.services.pipeline import (
                            apply_cross_version_comparison,
                        )

                        pipeline_result = apply_cross_version_comparison(
                            pipeline_result,
                            comparison_context.previous_data,
                        )

                # Step 4: Save to DB
                from data_extraction.services.save import save_pipeline_result

                candidate = save_pipeline_result(
                    pipeline_result=pipeline_result,
                    raw_text=raw_text,
                    category=category,
                    primary_file=primary,
                    other_files=others,
                    existing_ids=existing_ids,
                    comparison_context=comparison_context,
                    filename_meta=parsed,
                )

                if not candidate:
                    return False

            return True
        except Exception as e:
            # Last-resort: ensure a record exists even for unexpected errors
            try:
                self._save_failed_resume(
                    primary,
                    folder_name,
                    f"Unexpected error: {e}",
                    filename_meta=parsed,
                )
            except Exception:
                pass
            raise

    def _save_failed_resume(
        self,
        file_info: dict,
        folder_name: str,
        error_msg: str,
        *,
        filename_meta: dict | None = None,
    ):
        from data_extraction.services.save import save_failed_resume

        save_failed_resume(
            file_info, folder_name, error_msg, filename_meta=filename_meta
        )

    def _save_text_only_resume(
        self,
        file_info: dict,
        folder_name: str,
        *,
        raw_text: str,
        error_msg: str,
        filename_meta: dict | None = None,
    ):
        from data_extraction.services.save import save_text_only_resume

        save_text_only_resume(
            file_info,
            folder_name,
            raw_text=raw_text,
            error_msg=error_msg,
            filename_meta=filename_meta,
        )

    def _dry_run_report(self, groups: list[dict]):
        if not groups:
            self.stdout.write("  (no new files to process)")
            return

        self.stdout.write(f"\nWould process {len(groups)} groups:")
        for g in groups:
            primary = g["primary"]
            parsed = g["parsed"]
            folder = g["_folder_name"]
            name = parsed.get("name") or "(unparseable)"
            birth = parsed.get("birth_year") or "?"
            others_count = len(g["others"])
            self.stdout.write(
                f"  [{folder}] {name} ({birth}) - {primary['file_name']}"
                f"{f' + {others_count} more' if others_count else ''}"
            )

    def _print_summary(
        self,
        work_items: dict,
        succeeded: int,
        failed: int,
        total_sec: float,
        phase1_sec: float = 0,
        phase2_sec: float = 0,
        phase3_sec: float = 0,
        phase4_sec: float = 0,
        filtered: int = 0,
    ):
        self.stdout.write("\n=== Extract Summary ===")
        self.stdout.write(f"Total time: {total_sec:.1f}s")
        self.stdout.write(
            f"  Phase 1 (discover):   {phase1_sec:.1f}s\n"
            f"  Phase 2 (list files): {phase2_sec:.1f}s\n"
            f"  Phase 3 (filter):     {phase3_sec:.1f}s\n"
            f"  Phase 4 (process):    {phase4_sec:.1f}s"
        )
        self.stdout.write(f"Files: {work_items['total_files']}")
        self.stdout.write(f"Groups: {work_items['total_groups']}")
        self.stdout.write(f"Skipped (existing): {work_items['skipped']}")
        self.stdout.write(f"New: {len(work_items['new_groups'])}")
        self.stdout.write(self.style.SUCCESS(f"Succeeded: {succeeded}"))
        if filtered:
            self.stdout.write(self.style.WARNING(f"Filtered: {filtered}"))
        if failed:
            self.stdout.write(self.style.ERROR(f"Failed: {failed}"))
        else:
            self.stdout.write(f"Failed: {failed}")
        self.stdout.write("")

    # ------------------------------------------------------------------
    # Batch mode
    # ------------------------------------------------------------------

    def _handle_batch(self, options):
        step = options.get("step")

        if step == "prepare":
            return self._batch_prepare(options)
        elif step == "submit":
            return self._batch_submit(options)
        elif step == "poll":
            return self._batch_poll(options)
        elif step == "ingest":
            return self._batch_ingest(options)
        elif step == "next":
            return self._batch_next(options)
        else:
            # Full pipeline: prepare -> submit -> poll -> ingest
            return self._batch_full(options)

    def _get_job(self, job_id: str):
        from data_extraction.models import GeminiBatchJob

        try:
            return GeminiBatchJob.objects.get(id=job_id)
        except GeminiBatchJob.DoesNotExist:
            raise CommandError(f"Batch job {job_id} not found")

    def _batch_prepare(self, options):
        from data_extraction.models import GeminiBatchJob
        from data_extraction.services.batch.prepare import prepare_drive_job

        parent_folder_id = parse_drive_id(options["drive"])
        folder_filter = options.get("folder")
        limit = options.get("limit") or 0
        workers = options.get("workers") or 5

        display_name = f"extract-{time.strftime('%Y%m%d-%H%M%S')}"
        job = GeminiBatchJob.objects.create(display_name=display_name)

        self.stdout.write(f"\n=== Batch Prepare (Job #{job.id}) ===")

        t0 = time.time()
        job = prepare_drive_job(
            job=job,
            folder_name=folder_filter,
            limit=limit,
            parent_folder_id=parent_folder_id,
            workers=workers,
            force=options.get("force", False),
            retry_failed=options.get("retry_failed", False),
            failed_only=options.get("failed_only", False),
            shuffle=options.get("shuffle", False),
            integrity=options.get("integrity", False),
            birth_year_filter=options.get("birth_year_filter", False),
            birth_year_value=options.get("birth_year"),
        )
        elapsed = time.time() - t0

        self.stdout.write(f"Status: {job.get_status_display()}")
        self.stdout.write(f"Prepared: {job.total_requests} requests")
        self.stdout.write(f"Failed: {job.failed_requests} prepare failures")
        self.stdout.write(f"Request file: {job.request_file_path}")
        self.stdout.write(f"Time: {elapsed:.1f}s")
        self.stdout.write(self.style.SUCCESS(f"\nJob #{job.id} prepared."))
        return job

    def _batch_submit(self, options):
        from data_extraction.services.batch.api import (
            create_batch_job,
            upload_request_file,
        )

        job = self._get_job(options["job_id"])

        if not job.request_file_path:
            raise CommandError(f"Job #{job.id} has no request file (run prepare first)")

        self.stdout.write(f"\n=== Batch Submit (Job #{job.id}) ===")

        t0 = time.time()
        # Upload request file
        self.stdout.write("Uploading request file...")
        uploaded = upload_request_file(job.request_file_path, job.display_name)
        job.gemini_file_name = uploaded.name
        job.save(update_fields=["gemini_file_name", "updated_at"])

        # Create batch job
        self.stdout.write("Creating batch job...")
        remote_job = create_batch_job(
            model_name=job.model_name,
            file_name=uploaded.name,
            display_name=job.display_name,
        )
        job.gemini_batch_name = remote_job.name
        job.status = job.Status.SUBMITTED
        job.save(update_fields=["gemini_batch_name", "status", "updated_at"])
        elapsed = time.time() - t0

        self.stdout.write(f"Gemini batch name: {job.gemini_batch_name}")
        self.stdout.write(f"Time: {elapsed:.1f}s")
        self.stdout.write(self.style.SUCCESS(f"\nJob #{job.id} submitted."))
        return job

    def _batch_poll(self, options):
        from data_extraction.services.batch.api import (
            download_results_for_job,
            sync_job_from_remote,
        )

        job = self._get_job(options["job_id"])

        if not job.gemini_batch_name:
            raise CommandError(
                f"Job #{job.id} has no Gemini batch name (run submit first)"
            )

        self.stdout.write(f"\n=== Batch Poll (Job #{job.id}) ===")

        remote = sync_job_from_remote(job)
        job.refresh_from_db()

        self.stdout.write(f"Status: {job.get_status_display()}")
        self.stdout.write(f"Successful: {job.successful_requests}")
        self.stdout.write(f"Failed: {job.failed_requests}")

        if job.status == job.Status.SUCCEEDED:
            self.stdout.write("Downloading results...")
            result_path = download_results_for_job(job, remote=remote)
            if result_path:
                self.stdout.write(f"Result file: {result_path}")
                self.stdout.write(
                    self.style.SUCCESS("Results downloaded. Run --step ingest next.")
                )
            else:
                self.stdout.write(self.style.WARNING("No result file available yet."))
        elif job.status == job.Status.FAILED:
            self.stderr.write(self.style.ERROR(f"Job failed: {job.error_message}"))
        else:
            self.stdout.write("Job still running. Poll again later.")

        return job

    def _batch_ingest(self, options):
        from data_extraction.services.batch.ingest import ingest_job_results

        job = self._get_job(options["job_id"])
        workers = options.get("workers") or 1

        if not job.result_file_path:
            raise CommandError(
                f"Job #{job.id} has no result file (run poll after job succeeds)"
            )

        self.stdout.write(f"\n=== Batch Ingest (Job #{job.id}) ===")

        t0 = time.time()
        result = ingest_job_results(job, workers=workers)
        elapsed = time.time() - t0

        self.stdout.write(f"Processed: {result['processed']}")
        self.stdout.write(self.style.SUCCESS(f"Ingested: {result['ingested']}"))
        if result["failed"]:
            self.stdout.write(self.style.ERROR(f"Failed: {result['failed']}"))
        else:
            self.stdout.write(f"Failed: {result['failed']}")
        self.stdout.write(f"Time: {elapsed:.1f}s")
        self.stdout.write(self.style.SUCCESS(f"\nJob #{job.id} ingestion complete."))
        return job

    def _batch_next(self, options):
        from data_extraction.services.batch.integrity_chain import (
            prepare_next_integrity_job,
        )

        job = self._get_job(options["job_id"])
        if (job.metadata or {}).get("pipeline") != "integrity":
            raise CommandError(f"Job #{job.id} is not an integrity batch job")

        self.stdout.write(f"\n=== Batch Next (Job #{job.id}) ===")
        next_job = prepare_next_integrity_job(job)
        if next_job is None:
            self.stdout.write(self.style.SUCCESS("Integrity batch chain finalized."))
            return None
        self.stdout.write(f"Prepared next job: {next_job.id}")
        self.stdout.write(f"Stage: {(next_job.metadata or {}).get('stage')}")
        self.stdout.write(f"Requests: {next_job.total_requests}")
        self.stdout.write(f"Request file: {next_job.request_file_path}")
        return next_job

    def _batch_full(self, options):
        """Run all batch steps sequentially: prepare -> submit -> poll -> ingest."""
        self.stdout.write("\n=== Batch Full Pipeline ===")

        # Step 1: Prepare
        job = self._batch_prepare(options)

        if job.total_requests == 0:
            self.stdout.write("No requests to process. Stopping.")
            return

        # Step 2: Submit
        options["job_id"] = job.id
        job = self._batch_submit(options)

        job = self._poll_until_batch_complete(options)
        if job is None:
            return

        # Step 4: Ingest
        self._batch_ingest(options)

        if options.get("integrity"):
            current_job = job
            while True:
                next_job = self._batch_next({"job_id": current_job.id})
                if next_job is None:
                    self.stdout.write(
                        self.style.SUCCESS("\nFull batch pipeline complete.")
                    )
                    return
                options["job_id"] = next_job.id
                current_job = self._batch_submit(options)
                current_job = self._poll_until_batch_complete(options)
                if current_job is None:
                    return
                self._batch_ingest(options)

        self.stdout.write(self.style.SUCCESS("\nFull batch pipeline complete."))

    def _poll_until_batch_complete(self, options):
        self.stdout.write("\nPolling for completion...")
        poll_interval = 30
        max_polls = 120  # 1 hour max
        job = None
        for i in range(max_polls):
            time.sleep(poll_interval)
            job = self._batch_poll(options)
            if job.status in (job.Status.SUCCEEDED, job.Status.FAILED):
                break
            self.stdout.write(f"  Poll {i + 1}: still running...")

        if job is None or job.status == job.Status.FAILED:
            self.stderr.write(self.style.ERROR("Batch job failed. Stopping."))
            return None

        if job.status != job.Status.SUCCEEDED:
            self.stderr.write(self.style.WARNING("Batch job did not complete in time."))
            return None

        return job

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _handle_status(self, options):
        from data_extraction.models import GeminiBatchJob

        job_id = options.get("job_id")

        if job_id:
            job = self._get_job(job_id)
            self._print_job_detail(job)
        else:
            jobs = GeminiBatchJob.objects.all()[:20]
            if not jobs:
                self.stdout.write("No batch jobs found.")
                return
            self.stdout.write(f"\n=== Batch Jobs (latest {len(jobs)}) ===")
            self.stdout.write(
                f"{'ID':<38} {'Status':<12} {'Name':<30} {'Reqs':>5} {'OK':>5} "
                f"{'Fail':>5} {'Created'}"
            )
            self.stdout.write("-" * 110)
            for job in jobs:
                self.stdout.write(
                    f"{str(job.id):<38} {job.status:<12} {job.display_name:<30} "
                    f"{job.total_requests:>5} {job.successful_requests:>5} "
                    f"{job.failed_requests:>5} {job.created_at:%Y-%m-%d %H:%M}"
                )

    def _print_job_detail(self, job):
        self.stdout.write(f"\n=== Batch Job #{job.id} ===")
        self.stdout.write(f"Display name: {job.display_name}")
        self.stdout.write(f"Status: {job.get_status_display()}")
        self.stdout.write(f"Model: {job.model_name}")
        self.stdout.write(f"Source: {job.source}")
        metadata = job.metadata or {}
        if metadata.get("pipeline"):
            self.stdout.write(f"Pipeline: {metadata.get('pipeline')}")
        if metadata.get("stage"):
            self.stdout.write(f"Stage: {metadata.get('stage')}")
        if metadata.get("parent_job_id"):
            self.stdout.write(f"Parent job: {metadata.get('parent_job_id')}")
        self.stdout.write(f"Category filter: {job.category_filter or '(all)'}")
        self.stdout.write(f"Parent folder: {job.parent_folder_id or '(not set)'}")
        self.stdout.write(f"Total requests: {job.total_requests}")
        self.stdout.write(f"Successful: {job.successful_requests}")
        self.stdout.write(f"Failed: {job.failed_requests}")
        self.stdout.write(f"Request file: {job.request_file_path or '(none)'}")
        self.stdout.write(f"Result file: {job.result_file_path or '(none)'}")
        self.stdout.write(f"Gemini file: {job.gemini_file_name or '(none)'}")
        self.stdout.write(f"Gemini batch: {job.gemini_batch_name or '(none)'}")
        self.stdout.write(f"Created: {job.created_at:%Y-%m-%d %H:%M:%S}")
        self.stdout.write(f"Updated: {job.updated_at:%Y-%m-%d %H:%M:%S}")
        if job.error_message:
            self.stdout.write(self.style.ERROR(f"Error: {job.error_message}"))

        # Item summary
        item_counts = {}
        for item in job.items.all():
            item_counts[item.status] = item_counts.get(item.status, 0) + 1
        if item_counts:
            self.stdout.write("\nItem breakdown:")
            for status, count in sorted(item_counts.items()):
                self.stdout.write(f"  {status}: {count}")
