"""Migrate reason_left data from career_etc to Career.reason_left.

Uses composite key (company + start_date) for safe matching.
Falls back to company-only matching when exactly one Career matches.
Unmatched items are kept in career_etc (no data loss).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from candidates.models import Candidate
from candidates.services.etc_normalizer import (
    _CAREER_ETC_ALIASES,
    _CAREER_ETC_KEYWORDS,
    _canonicalize,
)
from data_extraction.services.extraction.integrity import (
    _normalize_company,
    _normalize_date_to_ym,
)


class Command(BaseCommand):
    help = "Migrate career_etc reason_left items to Career.reason_left"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without modifying data",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN ==="))

        candidates = Candidate.objects.exclude(career_etc=[]).exclude(career_etc__isnull=True)
        total_migrated = 0
        total_unmatched = 0
        total_candidates = 0

        for candidate in candidates:
            etc_items = candidate.career_etc or []
            careers = list(candidate.careers.all())
            remaining = []
            changed = False

            for item in etc_items:
                if _canonicalize(item, _CAREER_ETC_ALIASES, _CAREER_ETC_KEYWORDS) != "퇴사사유":
                    remaining.append(item)
                    continue

                etc_company = _normalize_company(
                    item.get("company") or item.get("name") or ""
                )
                etc_date = _normalize_date_to_ym(item.get("start_date") or "")

                matched_career = None

                # 1st: composite key match (company + start_date)
                if etc_company and etc_date:
                    for c in careers:
                        if (
                            _normalize_company(c.company) == etc_company
                            and c.start_date
                            and c.start_date == etc_date
                        ):
                            matched_career = c
                            break

                # 2nd: company-only match (only when exactly one Career)
                if not matched_career and etc_company:
                    company_matches = [
                        c for c in careers if _normalize_company(c.company) == etc_company
                    ]
                    if len(company_matches) == 1:
                        matched_career = company_matches[0]

                if matched_career and not matched_career.reason_left:
                    description = item.get("description", "")[:500]
                    if dry_run:
                        self.stdout.write(
                            f"  [{candidate.name}] {matched_career.company} "
                            f"← \"{description[:60]}...\""
                        )
                    else:
                        matched_career.reason_left = description
                        matched_career.save(update_fields=["reason_left"])
                    changed = True
                    total_migrated += 1
                else:
                    remaining.append(item)
                    if _canonicalize(item, _CAREER_ETC_ALIASES, _CAREER_ETC_KEYWORDS) == "퇴사사유":
                        total_unmatched += 1
                        if dry_run:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  [{candidate.name}] UNMATCHED: "
                                    f"{item.get('company', item.get('name', '?'))}"
                                )
                            )

            if changed:
                total_candidates += 1
                if not dry_run:
                    candidate.career_etc = remaining
                    candidate.save(update_fields=["career_etc"])

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Migrated: {total_migrated} items from {total_candidates} candidates"
            )
        )
        if total_unmatched:
            self.stdout.write(
                self.style.WARNING(f"Unmatched (kept in career_etc): {total_unmatched}")
            )
        if dry_run:
            self.stdout.write(self.style.WARNING("No changes made (dry run)"))
