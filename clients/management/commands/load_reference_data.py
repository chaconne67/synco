"""Load reference data from CSV fixtures.

Idempotent: re-running updates existing records and adds new ones.

Usage:
    uv run python manage.py load_reference_data
    uv run python manage.py load_reference_data --model universities
    uv run python manage.py load_reference_data --model companies
    uv run python manage.py load_reference_data --model certs
"""

from __future__ import annotations

import io
from pathlib import Path

from django.core.management.base import BaseCommand

from clients.models import CompanyProfile, PreferredCert, UniversityTier
from clients.services.csv_handler import import_csv

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"

MODEL_MAP = {
    "universities": (UniversityTier, "universities.csv"),
    "companies": (CompanyProfile, "companies.csv"),
    "certs": (PreferredCert, "certs.csv"),
}


class Command(BaseCommand):
    help = "Load reference data (universities, companies, certs) from CSV fixtures."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=list(MODEL_MAP.keys()),
            help="Load only the specified model. Default: all.",
        )

    def handle(self, *args, **options):
        targets = [options["model"]] if options["model"] else list(MODEL_MAP.keys())

        for key in targets:
            model, filename = MODEL_MAP[key]
            filepath = FIXTURES_DIR / filename
            if not filepath.exists():
                self.stderr.write(
                    self.style.WARNING(f"  Skipped {key}: {filepath} not found")
                )
                continue

            content = filepath.read_text(encoding="utf-8-sig")
            result = import_csv(model, io.StringIO(content))

            if result["errors"]:
                self.stderr.write(self.style.ERROR(f"  {key}: errors"))
                for err in result["errors"]:
                    self.stderr.write(f"    {err}")
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {key}: {result['created']} created, {result['updated']} updated"
                    )
                )
