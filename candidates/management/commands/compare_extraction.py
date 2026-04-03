"""Side-by-side comparison: Sonnet vs Gemini vs GPT-4o mini on new files.

Downloads resumes from Google Drive that are NOT in the DB,
extracts text, runs all models, and compares results.

Usage:
    uv run python manage.py compare_extraction --count 5
    uv run python manage.py compare_extraction --count 5 --verbose
    uv run python manage.py compare_extraction --count 5 --models sonnet,openai
    uv run python manage.py compare_extraction --count 5 --offset 5
"""

from __future__ import annotations

import json
import os
import tempfile
import time

from django.core.management.base import BaseCommand

from candidates.models import Resume
from candidates.services.drive_sync import (
    CATEGORY_FOLDERS,
    download_file,
    find_category_folder,
    get_drive_service,
    list_files_in_folder,
)
from candidates.services.text_extraction import extract_text, preprocess_resume_text

PARENT_FOLDER_ID = "1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"

COMPARE_FIELDS = [
    "name", "name_en", "birth_year", "gender", "email", "phone",
    "current_company", "current_position", "total_experience_years",
]

LIST_FIELDS = [
    ("careers", "company"),
    ("educations", "institution"),
    ("certifications", "name"),
]

# Model registry: name -> (extract_fn_import_path, label)
MODEL_REGISTRY = {
    "sonnet": {
        "label": "Sonnet",
        "import": ("candidates.services.llm_extraction", "extract_candidate_data"),
    },
    "gemini": {
        "label": "Gemini",
        "import": ("candidates.services.gemini_extraction", "extract_candidate_data"),
    },
}


def _load_extract_fn(model_key: str):
    """Dynamically import extraction function."""
    info = MODEL_REGISTRY[model_key]
    module_path, fn_name = info["import"]
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, fn_name)


def _norm(v) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def _find_new_files(service, max_count: int, offset: int = 0) -> list[dict]:
    """Find resume files in Drive not yet in DB."""
    new_files = []
    for cat_name in CATEGORY_FOLDERS:
        folder_id = find_category_folder(service, PARENT_FOLDER_ID, cat_name)
        if not folder_id:
            continue
        files = list_files_in_folder(service, folder_id)
        existing = set(
            Resume.objects.filter(drive_folder=cat_name).values_list("drive_file_id", flat=True)
        )
        for f in files:
            if f["id"] not in existing:
                new_files.append({**f, "category": cat_name})
    # Apply offset and limit
    return new_files[offset : offset + max_count]


class Command(BaseCommand):
    help = "Compare extraction quality across multiple models on new resume files"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5)
        parser.add_argument("--verbose", action="store_true")
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument(
            "--models",
            type=str,
            default="sonnet,gemini",
            help="Comma-separated model keys: sonnet,gemini",
        )

    def handle(self, *args, **options):
        count = options["count"]
        verbose = options["verbose"]
        offset = options["offset"]
        model_keys = [m.strip() for m in options["models"].split(",")]

        # Load extraction functions
        extractors = {}
        for key in model_keys:
            if key not in MODEL_REGISTRY:
                self.stderr.write(f"Unknown model: {key}. Available: {list(MODEL_REGISTRY.keys())}")
                return
            extractors[key] = _load_extract_fn(key)

        labels = {k: MODEL_REGISTRY[k]["label"] for k in model_keys}

        service = get_drive_service()

        self.stdout.write(f"\nFinding {count} unprocessed files (offset={offset})...")
        new_files = _find_new_files(service, count, offset)

        if not new_files:
            self.stderr.write("No unprocessed files found.")
            return

        model_names = " vs ".join(labels[k] for k in model_keys)
        self.stdout.write(f"Found {len(new_files)} files\n")
        self.stdout.write(f"{'='*70}")
        self.stdout.write(f" {model_names} Comparison")
        self.stdout.write(f"{'='*70}\n")

        # Per-model stats
        stats = {k: {"matches": 0, "total_fields": 0, "times": [], "failures": 0} for k in model_keys}
        file_results = []

        for i, file_info in enumerate(new_files, 1):
            fname = file_info["name"]
            fid = file_info["id"]
            cat = file_info["category"]

            self.stdout.write(f"\n--- [{i}/{len(new_files)}] {fname} ({cat}) ---")

            # 1. Download & extract text
            with tempfile.TemporaryDirectory() as tmpdir:
                dest = os.path.join(tmpdir, fname)
                try:
                    download_file(service, fid, dest)
                except Exception as e:
                    self.stderr.write(f"    Download failed: {e}")
                    continue
                try:
                    raw_text = extract_text(dest)
                except Exception as e:
                    self.stderr.write(f"    Text extraction failed: {e}")
                    continue

            if not raw_text.strip():
                self.stderr.write("    Empty text, skipping")
                continue

            preprocessed = preprocess_resume_text(raw_text)
            self.stdout.write(f"    Text: {len(raw_text):,} -> {len(preprocessed):,} chars")

            # 2. Run all models
            results = {}
            for key in model_keys:
                label = labels[key]
                self.stdout.write(f"    {label} extracting...", ending="")
                t0 = time.time()
                result = extractors[key](preprocessed)
                elapsed = time.time() - t0
                stats[key]["times"].append(elapsed)

                if result:
                    self.stdout.write(f" {elapsed:.1f}s, name={result.get('name')}")
                    results[key] = result
                else:
                    self.stdout.write(f" FAILED ({elapsed:.1f}s)")
                    stats[key]["failures"] += 1
                    results[key] = None

            # 3. Compare all pairs against first model (baseline)
            baseline_key = model_keys[0]
            baseline = results.get(baseline_key)
            if not baseline:
                continue

            for key in model_keys[1:]:
                other = results.get(key)
                if not other:
                    continue

                match_count = 0
                for field in COMPARE_FIELDS:
                    b_val = _norm(baseline.get(field))
                    o_val = _norm(other.get(field))
                    match = b_val == o_val
                    match_count += int(match)
                    if verbose:
                        icon = "O" if match else "X"
                        self.stdout.write(
                            f"      [{icon}] {field}: "
                            f"{labels[baseline_key]}={baseline.get(field)} | "
                            f"{labels[key]}={other.get(field)}"
                        )

                stats[key]["matches"] += match_count
                stats[key]["total_fields"] += len(COMPARE_FIELDS)

                self.stdout.write(
                    f"    {labels[baseline_key]} vs {labels[key]}: "
                    f"{match_count}/{len(COMPARE_FIELDS)} match"
                )

            # List field comparison
            for list_field, key_sub in LIST_FIELDS:
                parts = []
                for key in model_keys:
                    r = results.get(key)
                    cnt = len(r.get(list_field, []) or []) if r else 0
                    parts.append(f"{labels[key]}={cnt}")
                self.stdout.write(f"    {list_field}: {' / '.join(parts)}")

                if verbose:
                    for key in model_keys:
                        r = results.get(key)
                        if r:
                            items = r.get(list_field, []) or []
                            keys = [item.get(key_sub, "") for item in items]
                            self.stdout.write(f"      {labels[key]}: {keys}")

            file_results.append({
                "file": fname,
                "results": {k: results.get(k) for k in model_keys},
                "times": {k: stats[k]["times"][-1] for k in model_keys},
            })

        # Summary
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f" SUMMARY ({len(file_results)} files)")
        self.stdout.write(f"{'='*70}")

        baseline_label = labels[model_keys[0]]

        self.stdout.write(f"\n  Baseline: {baseline_label}")
        self.stdout.write(f"  {'Model':<15s} {'Match Rate':>12s} {'Avg Time':>10s} {'Failures':>10s}")
        self.stdout.write(f"  {'-'*15} {'-'*12} {'-'*10} {'-'*10}")

        for key in model_keys:
            label = labels[key]
            avg_time = sum(stats[key]["times"]) / len(stats[key]["times"]) if stats[key]["times"] else 0
            failures = stats[key]["failures"]

            if key == model_keys[0]:
                self.stdout.write(f"  {label:<15s} {'(baseline)':>12s} {avg_time:>9.1f}s {failures:>10d}")
            else:
                total_f = stats[key]["total_fields"]
                total_m = stats[key]["matches"]
                pct = total_m / total_f * 100 if total_f > 0 else 0
                self.stdout.write(
                    f"  {label:<15s} {total_m}/{total_f} ({pct:.0f}%){'':<1s} {avg_time:>9.1f}s {failures:>10d}"
                )

        self.stdout.write("")
