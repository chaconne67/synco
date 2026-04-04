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
    uv run python manage.py extract --batch --step submit --job-id 3
    uv run python manage.py extract --batch --step poll --job-id 3
    uv run python manage.py extract --batch --step ingest --job-id 3

    # Status
    uv run python manage.py extract --batch --status
    uv run python manage.py extract --batch --status --job-id 3
"""

from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError

from candidates.models import Category, Resume
from data_extraction.services.drive import (
    discover_folders,
    download_file,
    get_drive_service,
    list_all_files_parallel,
    parse_drive_id,
)
from data_extraction.services.filename import group_by_person
from data_extraction.services.pipeline import run_extraction_with_retry
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
            "--batch",
            action="store_true",
            help="Use batch mode (Gemini Batch API)",
        )
        parser.add_argument(
            "--step",
            type=str,
            choices=["prepare", "submit", "poll", "ingest"],
            help="Batch step: prepare, submit, poll, ingest",
        )
        parser.add_argument(
            "--job-id",
            type=int,
            help="Batch job ID (required for submit/poll/ingest steps)",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show batch job status",
        )

    def handle(self, *args, **options):
        self._validate_options(options)

        if options.get("status"):
            return self._handle_status(options)

        if options.get("batch"):
            return self._handle_batch(options)

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

        # --status doesn't require --drive
        if status:
            return

        # --step submit|poll|ingest requires --job-id
        if step in ("submit", "poll", "ingest") and not job_id:
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

        self.stdout.write(f"\n=== Extract {'(DRY RUN)' if dry_run else ''} ===")

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
                {"total_files": 0, "total_groups": 0, "skipped": 0,
                 "new_groups": [], "existing_ids": set(), "affected_folders": set()},
                0, 0, time.time() - start_time, phase1_sec,
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
                work_items, 0, 0, time.time() - start_time,
                phase1_sec, phase2_sec, phase3_sec,
            )
            return

        if not work_items["new_groups"]:
            self.stdout.write("Nothing new to process.")
            self._print_summary(
                work_items, 0, 0, time.time() - start_time,
                phase1_sec, phase2_sec, phase3_sec,
            )
            return

        # -- Phase 4: Process all new groups in parallel --
        t0 = time.time()
        succeeded, failed = self._process_all(
            work_items["new_groups"], workers, work_items["existing_ids"]
        )
        phase4_sec = time.time() - t0

        self.stdout.write(
            f"Phase 4 — Process: {succeeded} succeeded, {failed} failed ({phase4_sec:.1f}s)"
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
            work_items, succeeded, failed, time.time() - start_time,
            phase1_sec, phase2_sec, phase3_sec, phase4_sec,
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
            if limit:
                normalized = normalized[:limit]

            total_files += len(normalized)
            groups = group_by_person(normalized)
            folder_groups[folder_name] = groups
            total_groups += len(groups)

            for g in groups:
                all_file_ids.add(g["primary"]["file_id"])
                for other in g["others"]:
                    all_file_ids.add(other["file_id"])

        # Single bulk DB query
        existing_ids = set(
            Resume.objects.filter(drive_file_id__in=all_file_ids).values_list(
                "drive_file_id", flat=True,
            )
        )

        # Filter new groups
        for folder_name, groups in folder_groups.items():
            for g in groups:
                if g["primary"]["file_id"] in existing_ids:
                    total_skipped += 1
                else:
                    g["_folder_name"] = folder_name
                    all_new_groups.append(g)
                    affected_folders.add(folder_name)

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
    ) -> tuple[int, int]:
        """Process all groups in a single thread pool. Returns (succeeded, failed)."""
        succeeded = 0
        failed = 0

        # Pre-create categories
        folder_names = {g["_folder_name"] for g in groups}
        categories = {}
        for name in folder_names:
            categories[name], _ = Category.objects.get_or_create(
                name=name, defaults={"name_ko": ""},
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
                    if result:
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

        return succeeded, failed

    def _process_group(
        self,
        group: dict,
        folder_name: str,
        category: Category,
        existing_ids: set,
    ) -> bool:
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
    ) -> bool:
        primary = group["primary"]
        others = group["others"]
        parsed = group["parsed"]

        service = get_drive_service()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Download primary file
            dest_path = os.path.join(tmpdir, primary["file_name"])
            download_file(service, primary["file_id"], dest_path)

            # Step 2: Extract text + preprocess
            raw_text = extract_text(dest_path)
            if not raw_text or not raw_text.strip():
                self._save_failed_resume(primary, folder_name, "Empty text extraction")
                return False
            raw_text = preprocess_resume_text(raw_text)

            # Step 3: Extract + Validate + Retry
            pipeline_result = run_extraction_with_retry(
                raw_text=raw_text,
                file_path=dest_path,
                category=folder_name,
                filename_meta=parsed,
                file_reference_date=primary.get("modified_time"),
                use_integrity_pipeline=self.use_integrity,
            )

            extracted = pipeline_result["extracted"]
            if not extracted:
                self._save_text_only_resume(
                    primary,
                    folder_name,
                    raw_text=raw_text,
                    error_msg="Extraction failed after retries; stored raw text only",
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
            )

            if not candidate:
                return False

        return True

    def _save_failed_resume(self, file_info: dict, folder_name: str, error_msg: str):
        from data_extraction.services.save import save_failed_resume

        save_failed_resume(file_info, folder_name, error_msg)

    def _save_text_only_resume(
        self, file_info: dict, folder_name: str, *, raw_text: str, error_msg: str,
    ):
        from data_extraction.services.save import save_text_only_resume

        save_text_only_resume(file_info, folder_name, raw_text=raw_text, error_msg=error_msg)

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
        self, work_items: dict, succeeded: int, failed: int, total_sec: float,
        phase1_sec: float = 0, phase2_sec: float = 0,
        phase3_sec: float = 0, phase4_sec: float = 0,
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
        else:
            # Full pipeline: prepare -> submit -> poll -> ingest
            return self._batch_full(options)

    def _get_job(self, job_id: int):
        from batch_extract.models import GeminiBatchJob

        try:
            return GeminiBatchJob.objects.get(id=job_id)
        except GeminiBatchJob.DoesNotExist:
            raise CommandError(f"Batch job {job_id} not found")

    def _batch_prepare(self, options):
        from batch_extract.models import GeminiBatchJob
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
            raise CommandError(f"Job #{job.id} has no Gemini batch name (run submit first)")

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
                self.stdout.write(self.style.SUCCESS("Results downloaded. Run --step ingest next."))
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

        # Step 3: Poll until complete
        self.stdout.write("\nPolling for completion...")
        poll_interval = 30
        max_polls = 120  # 1 hour max
        for i in range(max_polls):
            time.sleep(poll_interval)
            job = self._batch_poll(options)
            if job.status in (job.Status.SUCCEEDED, job.Status.FAILED):
                break
            self.stdout.write(f"  Poll {i + 1}: still running...")

        if job.status == job.Status.FAILED:
            self.stderr.write(self.style.ERROR("Batch job failed. Stopping."))
            return

        if job.status != job.Status.SUCCEEDED:
            self.stderr.write(self.style.WARNING("Batch job did not complete in time."))
            return

        # Step 4: Ingest
        self._batch_ingest(options)
        self.stdout.write(self.style.SUCCESS("\nFull batch pipeline complete."))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _handle_status(self, options):
        from batch_extract.models import GeminiBatchJob

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
