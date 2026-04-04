"""Import resumes from Google Drive, extract text, parse via LLM, and save to DB.

Usage:
    # Google Drive URL or folder ID (auto-discovers subfolders)
    uv run python manage.py import_resumes --drive https://drive.google.com/drive/folders/1gPM...

    # Folder ID directly
    uv run python manage.py import_resumes --drive 1gPMDc7DZf_sirUx2QYzxRUAekLU0R7hy

    # Process a single subfolder
    uv run python manage.py import_resumes --drive <URL_OR_ID> --folder HR

    # Dry run
    uv run python manage.py import_resumes --drive <URL_OR_ID> --dry-run

    # Control parallelism
    uv run python manage.py import_resumes --drive <URL_OR_ID> --workers 3
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError

from candidates.models import Category, Resume
from candidates.services.drive_sync import (
    discover_folders,
    download_file,
    get_drive_service,
    list_all_files_parallel,
)
from candidates.services.filename_parser import group_by_person
from candidates.services.retry_pipeline import run_extraction_with_retry
from candidates.services.text_extraction import extract_text


class Command(BaseCommand):
    help = "Import resumes from Google Drive: download, extract text, LLM parse, save to DB"

    _DRIVE_FOLDER_RE = re.compile(r"(?:https?://[^/]+/drive/folders/)?([a-zA-Z0-9_-]+)")

    def add_arguments(self, parser):
        parser.add_argument(
            "--drive",
            type=str,
            required=True,
            help="Google Drive folder URL or ID (subfolders are auto-discovered)",
        )
        parser.add_argument(
            "--folder",
            type=str,
            help="Process only this subfolder name (e.g., 'HR')",
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
            "--workers",
            type=int,
            default=5,
            help="Parallel workers for processing (default: 5)",
        )
        parser.add_argument(
            "--integrity",
            action="store_true",
            help="Use integrity pipeline (Step 1→2→3) instead of legacy extraction",
        )

    def _parse_drive_id(self, value: str) -> str:
        match = self._DRIVE_FOLDER_RE.match(value.strip())
        if not match:
            raise CommandError(f"Cannot parse Drive folder ID from: {value}")
        return match.group(1)

    def handle(self, *args, **options):
        parent_folder_id = self._parse_drive_id(options["drive"])
        folder_filter = options.get("folder")
        limit = options.get("limit") or 0
        dry_run = options.get("dry_run")
        workers = options.get("workers")
        self.use_integrity = options.get("integrity", False)

        self.stdout.write(f"\n=== Resume Import {'(DRY RUN)' if dry_run else ''} ===")

        start_time = time.time()

        # ── Phase 1: Discover folders ──
        t0 = time.time()
        service = get_drive_service()
        folders = discover_folders(service, parent_folder_id)

        if folder_filter:
            folders = [f for f in folders if f["name"] == folder_filter]
            if not folders:
                self.stderr.write(f"Folder '{folder_filter}' not found under {parent_folder_id}.")
                return

        folder_names = [f["name"] for f in folders]
        phase1_sec = time.time() - t0
        self.stdout.write(
            f"Phase 1 — Discover: {len(folders)} folders found ({phase1_sec:.1f}s)"
        )
        self.stdout.write(f"  {', '.join(folder_names)}")

        # ── Phase 2: List files in all folders (parallel) ──
        t0 = time.time()
        if not folders:
            self.stdout.write("No folders found.")
            self._print_summary({"total_files": 0, "total_groups": 0, "skipped": 0,
                                  "new_groups": [], "existing_ids": set(),
                                  "affected_folders": set()},
                                0, 0, time.time() - start_time, phase1_sec)
            return

        folder_files = list_all_files_parallel(folders, workers=min(len(folders), 10))
        phase2_sec = time.time() - t0

        total_files = sum(len(files) for files in folder_files.values())
        self.stdout.write(
            f"Phase 2 — File listing: {total_files} files across "
            f"{len(folder_files)} folders ({phase2_sec:.1f}s)"
        )

        # ── Phase 3: Group, filter, and collect work items ──
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
            self._print_summary(work_items, 0, 0, time.time() - start_time,
                                phase1_sec, phase2_sec, phase3_sec)
            return

        if not work_items["new_groups"]:
            self.stdout.write("Nothing new to process.")
            self._print_summary(work_items, 0, 0, time.time() - start_time,
                                phase1_sec, phase2_sec, phase3_sec)
            return

        # ── Phase 4: Process all new groups in parallel ──
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

        self._print_summary(work_items, succeeded, failed, time.time() - start_time,
                            phase1_sec, phase2_sec, phase3_sec, phase4_sec)

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
                "drive_file_id", flat=True
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
                name=name, defaults={"name_ko": ""}
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
            from candidates.services.text_extraction import preprocess_resume_text

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
                    from candidates.services.retry_pipeline import (
                        apply_cross_version_comparison,
                    )

                    pipeline_result = apply_cross_version_comparison(
                        pipeline_result,
                        comparison_context.previous_data,
                    )

            # Step 4: Save to DB
            from candidates.services.integrity.save import save_pipeline_result

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
        from candidates.services.integrity.save import _save_failed_resume
        _save_failed_resume(file_info, folder_name, error_msg)

    def _save_text_only_resume(
        self, file_info: dict, folder_name: str, *, raw_text: str, error_msg: str,
    ):
        from candidates.services.integrity.save import _save_text_only_resume
        _save_text_only_resume(file_info, folder_name, raw_text=raw_text, error_msg=error_msg)

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
        self.stdout.write("\n=== Import Summary ===")
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
