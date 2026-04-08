"""CSV import/export for reference data models."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from django.db import transaction

from clients.models import CompanyProfile, PreferredCert, UniversityTier

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet


# --- Column definitions per model ---

COLUMNS: dict[type[Model], list[str]] = {
    UniversityTier: ["name", "name_en", "country", "tier", "ranking", "notes"],
    CompanyProfile: [
        "name",
        "name_en",
        "industry",
        "size_category",
        "revenue_range",
        "employee_count_range",
        "listed",
        "region",
        "notes",
    ],
    PreferredCert: ["name", "full_name", "category", "level", "aliases", "notes"],
}

# Upsert lookup keys per model
LOOKUP_KEYS: dict[type[Model], list[str]] = {
    UniversityTier: ["name", "country"],
    CompanyProfile: ["name"],
    PreferredCert: ["name"],
}

# Required columns (must be present in CSV header)
REQUIRED_COLUMNS: dict[type[Model], list[str]] = {
    UniversityTier: ["name", "country", "tier"],
    CompanyProfile: ["name"],
    PreferredCert: ["name", "category"],
}

# Fields with choices that need validation
_CHOICE_FIELDS: dict[type[Model], dict[str, set[str]]] = {
    UniversityTier: {
        "tier": {c.value for c in UniversityTier.Tier},
    },
    CompanyProfile: {
        "size_category": {c.value for c in CompanyProfile.SizeCategory} | {""},
        "listed": {c.value for c in CompanyProfile.Listed} | {""},
    },
    PreferredCert: {
        "category": {c.value for c in PreferredCert.Category},
        "level": {c.value for c in PreferredCert.Level} | {""},
    },
}


class _RollbackSignal(Exception):
    """Internal signal to trigger transaction rollback."""


def _parse_row(columns: list[str], row: dict[str, str]) -> dict:
    """Parse a CSV row into model field values."""
    data = {}
    for col in columns:
        val = row.get(col, "").strip()
        if col == "aliases":
            data[col] = [a.strip() for a in val.split(";") if a.strip()] if val else []
        elif col == "ranking":
            data[col] = int(val) if val else None
        else:
            data[col] = val
    return data


def import_csv(
    model: type[Model],
    file_obj: io.StringIO | io.TextIOWrapper,
) -> dict:
    """Import CSV data into a reference model.

    Single-pass: validate + upsert each row within one atomic transaction.
    On any error, entire transaction is rolled back.
    """
    errors: list[str] = []
    created = 0
    updated = 0

    try:
        reader = csv.DictReader(file_obj)
    except Exception as e:
        return {"created": 0, "updated": 0, "errors": [f"CSV 파싱 오류: {e}"]}

    if reader.fieldnames is None:
        return {"created": 0, "updated": 0, "errors": ["CSV 파일이 비어있습니다."]}

    # Header validation
    required = set(REQUIRED_COLUMNS.get(model, []))
    actual = set(reader.fieldnames)
    missing = required - actual
    if missing:
        return {
            "created": 0,
            "updated": 0,
            "errors": [f"필수 컬럼 누락: {', '.join(sorted(missing))}"],
        }

    columns = COLUMNS[model]
    choice_fields = _CHOICE_FIELDS.get(model, {})
    lookup_keys = LOOKUP_KEYS[model]

    try:
        with transaction.atomic():
            # First pass: validate all rows
            for row_num, row in enumerate(reader, start=2):
                data = _parse_row(columns, row)

                # Choice validation
                for field_name, valid_values in choice_fields.items():
                    val = data.get(field_name, "")
                    if val and val not in valid_values:
                        errors.append(
                            f"행 {row_num}: '{field_name}' 값 '{val}'이(가) 유효하지 않습니다."
                        )

                # Required field validation
                for req in REQUIRED_COLUMNS.get(model, []):
                    if not data.get(req):
                        errors.append(
                            f"행 {row_num}: 필수 필드 '{req}'이(가) 비어있습니다."
                        )

            if errors:
                raise _RollbackSignal()

            # Second pass: actual upsert (re-read from same data)
            file_obj.seek(0)
            reader2 = csv.DictReader(file_obj)
            for row in reader2:
                data = _parse_row(columns, row)

                lookup = {k: data[k] for k in lookup_keys}
                defaults = {k: v for k, v in data.items() if k not in lookup_keys}

                _, is_created = model.objects.update_or_create(
                    **lookup,
                    defaults=defaults,
                )
                if is_created:
                    created += 1
                else:
                    updated += 1

    except _RollbackSignal:
        pass  # errors list already populated

    return {"created": created, "updated": updated, "errors": errors}


def export_csv(model: type[Model], queryset: QuerySet) -> io.StringIO:
    """Export queryset to CSV StringIO with UTF-8 BOM.

    Returns StringIO with CSV content.
    """
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM for Excel compatibility

    columns = COLUMNS[model]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()

    for obj in queryset:
        row = {}
        for col in columns:
            val = getattr(obj, col, "")
            if col == "aliases" and isinstance(val, list):
                row[col] = ";".join(val)
            elif val is None:
                row[col] = ""
            else:
                row[col] = str(val)
        writer.writerow(row)

    return output
