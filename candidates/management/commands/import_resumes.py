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
from django.db import transaction

from candidates.models import (
    Candidate,
    Career,
    Category,
    Certification,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
    ValidationDiagnosis,
)
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

    def handle(self, *args, **options):
        folder = options.get("folder")
        process_all = options.get("all")
        limit = options.get("limit") or 0
        dry_run = options.get("dry_run")
        workers = options.get("workers")
        parent_folder_id = options.get("parent_folder_id")

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

            # Step 3: Extract + Validate + Retry (new pipeline)
            pipeline_result = run_extraction_with_retry(
                raw_text=raw_text,
                file_path=dest_path,
                category=folder_name,
                filename_meta=parsed,
            )

            extracted = pipeline_result["extracted"]
            if not extracted:
                self._save_failed_resume(
                    primary, folder_name, "Extraction failed after retries"
                )
                return False

            # Use potentially re-extracted text
            raw_text = pipeline_result["raw_text_used"]

            # Step 3.5: Fallback name from filename if LLM returned null
            if not extracted.get("name"):
                extracted["name"] = parsed.get("name") or primary["file_name"]

            # Step 4: Build validation result from Codex diagnosis
            diagnosis = pipeline_result["diagnosis"]
            field_confidences = extracted.get("field_confidences", {})
            validation = {
                "confidence_score": diagnosis.get("overall_score", 0.0),
                "validation_status": (
                    "auto_confirmed"
                    if diagnosis["verdict"] == "pass"
                    else "needs_review"
                    if diagnosis.get("overall_score", 0) >= 0.6
                    else "failed"
                ),
                "field_confidences": {
                    **field_confidences,
                    **diagnosis.get("field_scores", {}),
                },
                "issues": diagnosis.get("issues", []),
            }

            # Step 5: Save to DB in a transaction
            with transaction.atomic():
                candidate = self._create_candidate(
                    extracted=extracted,
                    raw_text=raw_text,
                    validation=validation,
                    category=category,
                )

                # Create child records
                self._create_educations(candidate, extracted.get("educations", []))
                self._create_careers(candidate, extracted.get("careers", []))
                self._create_certifications(
                    candidate, extracted.get("certifications", [])
                )
                self._create_language_skills(
                    candidate, extracted.get("language_skills", [])
                )

                # Create primary resume
                primary_resume = Resume.objects.create(
                    candidate=candidate,
                    file_name=primary["file_name"],
                    drive_file_id=primary["file_id"],
                    drive_folder=folder_name,
                    mime_type=primary.get("mime_type", ""),
                    file_size=primary.get("file_size"),
                    raw_text=raw_text,
                    is_primary=True,
                    version=1,
                    processing_status=Resume.ProcessingStatus.PARSED,
                )

                # Create resumes for other versions
                for idx, other in enumerate(others):
                    if other["file_id"] not in existing_ids:
                        Resume.objects.create(
                            candidate=candidate,
                            file_name=other["file_name"],
                            drive_file_id=other["file_id"],
                            drive_folder=folder_name,
                            mime_type=other.get("mime_type", ""),
                            file_size=other.get("file_size"),
                            is_primary=False,
                            version=idx + 2,
                            processing_status=Resume.ProcessingStatus.PENDING,
                        )

                # Create extraction log
                ExtractionLog.objects.create(
                    candidate=candidate,
                    resume=primary_resume,
                    action=ExtractionLog.Action.AUTO_EXTRACT,
                    field_name="full_extraction",
                    new_value=str(extracted),
                    confidence=validation["confidence_score"],
                    note=f"Imported from Drive folder: {folder_name}",
                )

                # Save validation diagnosis from retry pipeline
                ValidationDiagnosis.objects.create(
                    candidate=candidate,
                    resume=primary_resume,
                    attempt_number=pipeline_result["attempts"],
                    verdict=diagnosis["verdict"],
                    overall_score=diagnosis.get("overall_score", 0.0),
                    issues=diagnosis.get("issues", []),
                    field_scores=diagnosis.get("field_scores", {}),
                    retry_action=pipeline_result["retry_action"],
                )

                # Add category
                candidate.categories.add(category)

        return True

    def _create_candidate(
        self,
        extracted: dict,
        raw_text: str,
        validation: dict,
        category: Category,
    ) -> Candidate:
        """Create a Candidate from extracted data."""
        return Candidate.objects.create(
            name=extracted.get("name") or "",
            name_en=extracted.get("name_en") or "",
            birth_year=extracted.get("birth_year"),
            gender=extracted.get("gender") or "",
            email=extracted.get("email") or "",
            phone=extracted.get("phone") or "",
            address=extracted.get("address") or "",
            current_company=extracted.get("current_company") or "",
            current_position=extracted.get("current_position") or "",
            total_experience_years=extracted.get("total_experience_years"),
            core_competencies=extracted.get("core_competencies", []),
            summary=extracted.get("summary") or "",
            status=Candidate.Status.ACTIVE,
            source=Candidate.Source.DRIVE_IMPORT,
            raw_text=raw_text,
            validation_status=validation["validation_status"],
            raw_extracted_json=extracted,
            confidence_score=validation["confidence_score"],
            field_confidences=validation.get("field_confidences", {}),
            primary_category=category,
        )

    def _create_educations(self, candidate: Candidate, educations: list[dict]):
        """Create Education records from extracted data."""
        for edu in educations:
            Education.objects.create(
                candidate=candidate,
                institution=edu.get("institution") or "",
                degree=edu.get("degree") or "",
                major=edu.get("major") or "",
                gpa=str(edu.get("gpa") or ""),
                start_year=edu.get("start_year"),
                end_year=edu.get("end_year"),
                is_abroad=edu.get("is_abroad", False),
            )

    def _create_careers(self, candidate: Candidate, careers: list[dict]):
        """Create Career records from extracted data."""
        for career in careers:
            Career.objects.create(
                candidate=candidate,
                company=career.get("company") or "",
                company_en=career.get("company_en") or "",
                position=career.get("position") or "",
                department=career.get("department") or "",
                start_date=career.get("start_date") or "",
                end_date=career.get("end_date") or "",
                is_current=career.get("is_current", False),
                duties=career.get("duties") or "",
                achievements=career.get("achievements") or "",
                reason_left=career.get("reason_left") or "",
                salary=career.get("salary"),
                order=career.get("order", 0),
            )

    def _create_certifications(self, candidate: Candidate, certifications: list[dict]):
        """Create Certification records from extracted data."""
        for cert in certifications:
            Certification.objects.create(
                candidate=candidate,
                name=cert.get("name") or "",
                issuer=cert.get("issuer") or "",
                acquired_date=cert.get("acquired_date") or "",
            )

    def _create_language_skills(
        self, candidate: Candidate, language_skills: list[dict]
    ):
        """Create LanguageSkill records from extracted data."""
        for lang in language_skills:
            LanguageSkill.objects.create(
                candidate=candidate,
                language=lang.get("language") or "",
                test_name=lang.get("test_name") or "",
                score=lang.get("score") or "",
                level=lang.get("level") or "",
            )

    def _save_failed_resume(self, file_info: dict, folder_name: str, error_msg: str):
        """Save a resume record with FAILED status for tracking."""
        Resume.objects.create(
            file_name=file_info["file_name"],
            drive_file_id=file_info["file_id"],
            drive_folder=folder_name,
            mime_type=file_info.get("mime_type", ""),
            file_size=file_info.get("file_size"),
            processing_status=Resume.ProcessingStatus.FAILED,
            error_message=error_msg,
        )

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
