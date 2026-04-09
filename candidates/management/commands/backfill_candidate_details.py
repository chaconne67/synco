"""Backfill candidate detail fields from raw_extracted_json.

Parses existing raw_extracted_json for all candidates and populates
the new detail fields: salary, military, awards, overseas, self_intro,
family, trainings, patents, projects.

Usage:
    uv run python manage.py backfill_candidate_details          # all candidates
    uv run python manage.py backfill_candidate_details --dry-run # preview only
    uv run python manage.py backfill_candidate_details --field salary  # specific field
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from candidates.models import Candidate
from candidates.services.detail_normalizers import (
    normalize_awards,
    normalize_family,
    normalize_military,
    normalize_overseas,
    normalize_patents,
    normalize_projects,
    normalize_self_intro,
    normalize_trainings,
)
from candidates.services.salary_parser import normalize_salary

# All supported fields
ALL_FIELDS = [
    "salary",
    "military",
    "awards",
    "overseas",
    "self_intro",
    "family",
    "trainings",
    "patents",
    "projects",
]


class Command(BaseCommand):
    help = "Backfill candidate detail fields from raw_extracted_json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving",
        )
        parser.add_argument(
            "--field",
            type=str,
            choices=ALL_FIELDS,
            help="Process only a specific field",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        field_filter = options.get("field")

        fields_to_process = [field_filter] if field_filter else ALL_FIELDS

        self.stdout.write(
            f"\n=== Backfill Candidate Details {'(DRY RUN)' if dry_run else ''} ==="
        )
        self.stdout.write(f"Fields: {', '.join(fields_to_process)}")

        candidates = Candidate.objects.all()
        total = candidates.count()
        self.stdout.write(f"Total candidates: {total}\n")

        stats = {f: 0 for f in ALL_FIELDS}
        updated_count = 0

        for candidate in candidates.iterator():
            raw = candidate.raw_extracted_json or {}
            if not raw:
                continue

            changed = False
            update_fields = []

            # 1. Salary
            if "salary" in fields_to_process:
                salary_result = normalize_salary(raw)
                if salary_result["current_salary_int"] and not candidate.current_salary:
                    candidate.current_salary = salary_result["current_salary_int"]
                    update_fields.append("current_salary")
                    changed = True
                if salary_result["desired_salary_int"] and not candidate.desired_salary:
                    candidate.desired_salary = salary_result["desired_salary_int"]
                    update_fields.append("desired_salary")
                    changed = True
                if salary_result["salary_detail"] and not candidate.salary_detail:
                    candidate.salary_detail = salary_result["salary_detail"]
                    update_fields.append("salary_detail")
                    changed = True
                if salary_result["salary_detail"]:
                    stats["salary"] += 1

            # 2. Military
            if "military" in fields_to_process:
                military_raw = (
                    raw.get("military_service") or raw.get("military") or None
                )
                if military_raw and not candidate.military_service:
                    candidate.military_service = normalize_military(military_raw)
                    update_fields.append("military_service")
                    changed = True
                    stats["military"] += 1

            # 3. Awards
            if "awards" in fields_to_process:
                awards_raw = raw.get("awards") or raw.get("honors") or None
                if awards_raw and not candidate.awards:
                    candidate.awards = normalize_awards(awards_raw)
                    update_fields.append("awards")
                    changed = True
                    stats["awards"] += 1

            # 4. Self-introduction
            if "self_intro" in fields_to_process:
                self_intro_raw = (
                    raw.get("self_introduction")
                    or raw.get("personal_statement")
                    or raw.get("cover_letter")
                    or raw.get("objective")
                    or None
                )
                if self_intro_raw and not candidate.self_introduction:
                    candidate.self_introduction = normalize_self_intro(self_intro_raw)
                    update_fields.append("self_introduction")
                    changed = True
                    stats["self_intro"] += 1

            # 5. Family
            if "family" in fields_to_process:
                family_raw = (
                    raw.get("family_info")
                    or raw.get("family_background")
                    or raw.get("marital_status")
                    or None
                )
                if family_raw and not candidate.family_info:
                    candidate.family_info = normalize_family(family_raw)
                    update_fields.append("family_info")
                    changed = True
                    stats["family"] += 1

            # 6. Overseas
            if "overseas" in fields_to_process:
                overseas_raw = (
                    raw.get("overseas_experience")
                    or raw.get("international_experience")
                    or raw.get("residence_abroad")
                    or None
                )
                if overseas_raw and not candidate.overseas_experience:
                    candidate.overseas_experience = normalize_overseas(overseas_raw)
                    update_fields.append("overseas_experience")
                    changed = True
                    stats["overseas"] += 1

            # 7. Trainings
            if "trainings" in fields_to_process:
                trainings_raw = (
                    raw.get("trainings")
                    or raw.get("training_courses")
                    or raw.get("training_programs")
                    or raw.get("education_history")
                    or None
                )
                if trainings_raw and not candidate.trainings:
                    candidate.trainings = normalize_trainings(trainings_raw)
                    update_fields.append("trainings")
                    changed = True
                    stats["trainings"] += 1

            # 8. Patents
            if "patents" in fields_to_process:
                patents_raw = (
                    raw.get("patents_registered")
                    or raw.get("patents_applications")
                    or raw.get("patents")
                    or None
                )
                if patents_raw and not candidate.patents:
                    candidate.patents = normalize_patents(patents_raw)
                    update_fields.append("patents")
                    changed = True
                    stats["patents"] += 1

            # 9. Projects
            if "projects" in fields_to_process:
                projects_raw = raw.get("projects") or None
                if projects_raw and not candidate.projects:
                    candidate.projects = normalize_projects(projects_raw)
                    update_fields.append("projects")
                    changed = True
                    stats["projects"] += 1

            if changed:
                updated_count += 1
                if dry_run:
                    self.stdout.write(
                        f"  [DRY] {candidate.name}: would update {', '.join(update_fields)}"
                    )
                else:
                    candidate.save(update_fields=update_fields + ["updated_at"])

        # Print summary
        self.stdout.write(f"\n=== Backfill Summary ===")
        self.stdout.write(f"Total candidates scanned: {total}")
        self.stdout.write(f"Candidates updated: {updated_count}")
        self.stdout.write(f"\nPer-field counts:")
        for field in fields_to_process:
            self.stdout.write(f"  {field}: {stats[field]}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n(DRY RUN - no changes saved)"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nBackfill complete. {updated_count} candidates updated."
                )
            )
