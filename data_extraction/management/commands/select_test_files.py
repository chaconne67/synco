"""단계별 검증을 위해 카테고리별로 N개씩 random 파일 ID 선정.

Usage:
    uv run python manage.py select_test_files \\
        --drive 1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y \\
        --per-category 2 \\
        --seed 42 \\
        --output snapshots/test40_ids.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from django.core.management.base import BaseCommand

from data_extraction.services.drive import (
    discover_folders,
    get_drive_service,
    list_all_files_parallel,
)
from data_extraction.services.filename import group_by_person


class Command(BaseCommand):
    help = "Select N random files per Drive category for staged verification."

    def add_arguments(self, parser):
        parser.add_argument("--drive", type=str, required=True)
        parser.add_argument("--per-category", type=int, default=2)
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Random seed (재현 가능한 선택). 비우면 비결정",
        )
        parser.add_argument("--output", type=str, required=True)
        parser.add_argument(
            "--group-by-person",
            action="store_true",
            help="파일명 휴리스틱으로 person grouping 후 그룹 단위로 선정",
        )

    def handle(self, *args, **options):
        rng = random.Random(options.get("seed"))
        per_cat = options["per_category"]
        out_path = Path(options["output"])

        service = get_drive_service()
        self.stdout.write("Discovering categories...")
        folders = discover_folders(service, options["drive"])
        self.stdout.write(f"  → {len(folders)} categories")

        self.stdout.write("Listing files per category (parallel)...")
        folder_files = list_all_files_parallel(folders, workers=min(len(folders), 10))

        selected = []
        per_cat_summary = {}
        for folder_name, files in sorted(folder_files.items()):
            if not files:
                per_cat_summary[folder_name] = {"total": 0, "selected": 0}
                continue

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

            if options["group_by_person"]:
                groups = group_by_person(normalized)
                pool = [g["primary"] for g in groups]
            else:
                pool = normalized

            n_pick = min(per_cat, len(pool))
            picks = rng.sample(pool, n_pick)
            for p in picks:
                selected.append(
                    {
                        "category": folder_name,
                        "file_id": p["file_id"],
                        "file_name": p["file_name"],
                        "mime_type": p["mime_type"],
                        "file_size": p["file_size"],
                        "modified_time": p["modified_time"],
                    }
                )
            per_cat_summary[folder_name] = {
                "total": len(pool),
                "selected": n_pick,
            }

        payload = {
            "drive_parent_id": options["drive"],
            "per_category": per_cat,
            "seed": options.get("seed"),
            "group_by_person": options["group_by_person"],
            "category_summary": per_cat_summary,
            "total_selected": len(selected),
            "files": selected,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Selected {len(selected)} files"))
        self.stdout.write(f"Saved to: {out_path}")
        self.stdout.write("")
        self.stdout.write("카테고리별 선정 결과:")
        for cat, info in sorted(per_cat_summary.items()):
            self.stdout.write(
                f"  {cat:15} {info['selected']:>2} / {info['total']:>4} 파일"
            )
