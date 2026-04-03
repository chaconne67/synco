"""Import resumes from Google Drive, extract text, parse via LLM, and save to DB.

Usage:
    # Process a single category folder
    uv run python manage.py import_resumes --folder Accounting

    # Process all 20 category folders
    uv run python manage.py import_resumes --all

    # Dry run (list files without processing)
    uv run python manage.py import_resumes --all --dry-run

    # Limit files per folder
    uv run python manage.py import_resumes --folder HR --limit 5

    # Control parallelism
    uv run python manage.py import_resumes --all --workers 3
"""

from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError

from candidates.models import Category, Resume
from candidates.services.drive_sync import (
    CATEGORY_FOLDERS,
    download_file,
    find_category_folder,
    get_drive_service,
    list_files_in_folder,
)
from candidates.services.filename_parser import group_by_person
from candidates.services.retry_pipeline import run_extraction_with_retry
from candidates.services.text_extraction import extract_text


class Command(BaseCommand):
    help = "Import resumes from Google Drive: download, extract text, LLM parse, save to DB"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--folder",
            type=str,
            help="Specific category folder name (e.g., 'Accounting')",
        )
        group.add_argument(
            "--all",
            action="store_true",
            help="Process all 20 category folders",
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
            help="ThreadPoolExecutor max_workers (default: 5)",
        )
        parser.add_argument(
            "--parent-folder-id",
            type=str,
            default="root",
            help="Parent folder ID on Drive (default: root)",
        )
        parser.add_argument(
            "--integrity",
            action="store_true",
            help="Use new integrity pipeline (Step 1→1.5→2→3) instead of legacy extraction",
        )

    def handle(self, *args, **options):
        folder = options.get("folder")
        process_all = options.get("all")
        limit = options.get("limit") or 0
        dry_run = options.get("dry_run")
        workers = options.get("workers")
        parent_folder_id = options.get("parent_folder_id")
        self.use_integrity = options.get("integrity", False)

        # Determine which folders to process
        if process_all:
            folders = list(CATEGORY_FOLDERS)
        else:
            if folder not in CATEGORY_FOLDERS:
                raise CommandError(
                    f"Unknown folder '{folder}'. "
                    f"Valid folders: {', '.join(CATEGORY_FOLDERS)}"
                )
            folders = [folder]

        self.stdout.write(f"\n=== Resume Import {'(DRY RUN)' if dry_run else ''} ===")
        self.stdout.write(
            f"Folders: {len(folders)}, Limit: {limit or 'unlimited'}, Workers: {workers}"
        )

        # Connect to Drive
        service = get_drive_service()
        self.stdout.write("Google Drive connected.\n")

        # Track stats
        stats = {
            "folders_processed": 0,
            "files_found": 0,
            "groups_found": 0,
            "skipped_existing": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
        }
        start_time = time.time()

        for folder_name in folders:
            self._process_folder(
                service=service,
                folder_name=folder_name,
                parent_folder_id=parent_folder_id,
                limit=limit,
                dry_run=dry_run,
                workers=workers,
                stats=stats,
            )

        elapsed = time.time() - start_time
        self._print_summary(stats, elapsed)

    def _process_folder(
        self,
        service,
        folder_name: str,
        parent_folder_id: str,
        limit: int,
        dry_run: bool,
        workers: int,
        stats: dict,
    ):
        """Process a single category folder."""
        self.stdout.write(f"\n--- {folder_name} ---")

        # Find folder on Drive
        folder_id = find_category_folder(service, parent_folder_id, folder_name)
        if not folder_id:
            self.stderr.write(f"  Folder '{folder_name}' not found on Drive. Skipping.")
            return

        # List files
        files = list_files_in_folder(service, folder_id)
        if not files:
            self.stdout.write(f"  No files found in '{folder_name}'.")
            return

        # Normalize file dicts: ensure consistent keys for group_by_person
        normalized = []
        for f in files:
            normalized.append(
                {
                    "file_name": f["name"],
                    "file_id": f["id"],
                    "mime_type": f.get("mimeType", ""),
                    "file_size": int(f.get("size", 0)) if f.get("size") else 0,
                    "modified_time": f.get("modifiedTime", ""),
                }
            )

        # Apply limit
        if limit:
            normalized = normalized[:limit]

        stats["files_found"] += len(normalized)

        # Group by person
        groups = group_by_person(normalized)
        stats["groups_found"] += len(groups)

        self.stdout.write(f"  Files: {len(normalized)}, Groups: {len(groups)}")

        # Filter out already-imported files (idempotency)
        all_file_ids = set()
        for g in groups:
            all_file_ids.add(g["primary"]["file_id"])
            for other in g["others"]:
                all_file_ids.add(other["file_id"])

        existing_ids = set(
            Resume.objects.filter(drive_file_id__in=all_file_ids).values_list(
                "drive_file_id", flat=True
            )
        )

        # Filter groups: skip if primary already imported
        new_groups = []
        for g in groups:
            if g["primary"]["file_id"] in existing_ids:
                stats["skipped_existing"] += 1
                continue
            new_groups.append(g)

        skipped = len(groups) - len(new_groups)
        if skipped:
            self.stdout.write(f"  Skipping {skipped} already-imported groups")

        if dry_run:
            self._dry_run_report(new_groups, folder_name)
            stats["folders_processed"] += 1
            return

        if not new_groups:
            self.stdout.write("  Nothing new to process.")
            stats["folders_processed"] += 1
            return

        # Ensure category exists
        category, _ = Category.objects.get_or_create(
            name=folder_name,
            defaults={"name_ko": ""},
        )

        # Process groups in parallel (LLM calls are the bottleneck)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for group in new_groups:
                future = executor.submit(
                    self._process_group,
                    service=service,
                    group=group,
                    folder_name=folder_name,
                    category=category,
                    existing_ids=existing_ids,
                )
                futures[future] = group

            for future in as_completed(futures):
                group = futures[future]
                primary_name = group["primary"]["file_name"]
                stats["processed"] += 1
                try:
                    result = future.result()
                    if result:
                        stats["succeeded"] += 1
                        self.stdout.write(self.style.SUCCESS(f"  OK: {primary_name}"))
                    else:
                        stats["failed"] += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  SKIP: {primary_name} (extraction failed)"
                            )
                        )
                except Exception as e:
                    stats["failed"] += 1
                    self.stderr.write(f"  FAIL: {primary_name}: {e}")

        # Update category candidate count
        category.candidate_count = category.candidates.count()
        category.save(update_fields=["candidate_count"])

        stats["folders_processed"] += 1

    def _process_group(
        self,
        service,
        group: dict,
        folder_name: str,
        category: Category,
        existing_ids: set,
    ) -> bool:
        """Process a single person group: download, extract, LLM, validate, save.

        Returns True if successful, False if skipped/failed.
        """
        primary = group["primary"]
        others = group["others"]
        parsed = group["parsed"]

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
                use_integrity_pipeline=getattr(self, "use_integrity", False),
            )

            extracted = pipeline_result["extracted"]
            if not extracted:
                self._save_failed_resume(
                    primary, folder_name, "Extraction failed after retries"
                )
                return False

            # Use potentially re-extracted text
            raw_text = pipeline_result["raw_text_used"]

            # Fallback name from filename if LLM returned null
            if not extracted.get("name"):
                extracted["name"] = parsed.get("name") or primary["file_name"]

            comparison_context = None
            if extracted:
                from candidates.services.candidate_identity import (
                    build_candidate_comparison_context,
                )

                comparison_context = build_candidate_comparison_context(extracted)
                if (
                    getattr(self, "use_integrity", False)
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
        """Save a resume record with FAILED status for tracking."""
        from candidates.services.integrity.save import _save_failed_resume
        _save_failed_resume(file_info, folder_name, error_msg)

    def _dry_run_report(self, groups: list[dict], folder_name: str):
        """Print a dry-run report of files that would be processed."""
        if not groups:
            self.stdout.write("  (no new files to process)")
            return

        self.stdout.write(f"  Would process {len(groups)} groups:")
        for g in groups:
            primary = g["primary"]
            parsed = g["parsed"]
            others_count = len(g["others"])
            name = parsed.get("name") or "(unparseable)"
            birth = parsed.get("birth_year") or "?"
            self.stdout.write(
                f"    {name} ({birth}) - {primary['file_name']}"
                f"{f' + {others_count} more' if others_count else ''}"
            )

    def _print_summary(self, stats: dict, elapsed: float):
        """Print final summary statistics."""
        self.stdout.write("\n=== Import Summary ===")
        self.stdout.write(f"Time: {elapsed:.1f}s")
        self.stdout.write(f"Folders processed: {stats['folders_processed']}")
        self.stdout.write(f"Files found: {stats['files_found']}")
        self.stdout.write(f"Groups found: {stats['groups_found']}")
        self.stdout.write(f"Skipped (existing): {stats['skipped_existing']}")
        self.stdout.write(f"Processed: {stats['processed']}")
        self.stdout.write(self.style.SUCCESS(f"Succeeded: {stats['succeeded']}"))
        if stats["failed"]:
            self.stdout.write(self.style.ERROR(f"Failed: {stats['failed']}"))
        else:
            self.stdout.write(f"Failed: {stats['failed']}")
        self.stdout.write("")
