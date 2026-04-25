"""Step B2 — 다운로드된 파일에서 텍스트 추출 + 전처리.

각 파일에 대해 raw 텍스트와 전처리 후 텍스트를 동시 측정하여
전처리가 무엇을 변화시켰는지 가시화합니다.

Usage:
    uv run python manage.py verify_text_extract \\
        --input snapshots/step_b1_download.json \\
        --output snapshots/step_b2_text.json \\
        --text-dir snapshots/test40_texts
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand

from data_extraction.services.text import (
    extract_text,
    preprocess_resume_text,
)


class Command(BaseCommand):
    help = "Step B2: extract + preprocess text from downloaded files."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True)
        parser.add_argument("--output", type=str, required=True)
        parser.add_argument(
            "--text-dir",
            type=str,
            required=True,
            help="전처리된 텍스트를 저장할 디렉터리 (다음 단계 입력)",
        )

    def handle(self, *args, **options):
        in_path = Path(options["input"])
        out_path = Path(options["output"])
        text_dir = Path(options["text_dir"])
        text_dir.mkdir(parents=True, exist_ok=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        spec = json.loads(in_path.read_text(encoding="utf-8"))
        files = spec.get("results", [])
        downloaded = [f for f in files if f.get("ok")]

        results = []
        succeeded = 0
        failed = 0
        total_seconds = 0.0
        empty_after_preprocess = 0

        self.stdout.write(f"Extracting text from {len(downloaded)} files")
        self.stdout.write("")

        for idx, f in enumerate(downloaded, start=1):
            saved_path = f["saved_path"]
            t0 = time.time()
            raw = ""
            preprocessed = ""
            error = ""
            ok = False
            try:
                raw = extract_text(saved_path)
                preprocessed = preprocess_resume_text(raw)
                ok = True
                succeeded += 1
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                failed += 1
            elapsed = time.time() - t0
            total_seconds += elapsed

            raw_len = len(raw)
            pre_len = len(preprocessed)
            if ok and pre_len == 0:
                empty_after_preprocess += 1

            text_path = ""
            if ok and pre_len > 0:
                text_path = str(text_dir / f"{f['file_id']}.txt")
                Path(text_path).write_text(preprocessed, encoding="utf-8")

            preview = preprocessed[:120].replace("\n", " ⏎ ") if preprocessed else "(empty)"
            line = (
                f"  [{idx:>2}/{len(downloaded)}] [{f['category']:<12}] "
                f"{'OK ' if ok else 'FAIL'} "
                f"raw={raw_len:>6d} pre={pre_len:>6d} ({elapsed:>4.2f}s)  "
                f"{f['file_name'][:35]:<35} | {preview[:60]}"
            )
            if not ok:
                line += f"  ← {error}"
            self.stdout.write(line)

            results.append(
                {
                    "category": f["category"],
                    "file_id": f["file_id"],
                    "file_name": f["file_name"],
                    "saved_path": saved_path,
                    "text_path": text_path,
                    "raw_length": raw_len,
                    "preprocessed_length": pre_len,
                    "shrink_ratio": (
                        round((raw_len - pre_len) / raw_len, 3) if raw_len > 0 else 0
                    ),
                    "elapsed_seconds": round(elapsed, 3),
                    "ok": ok,
                    "empty_after_preprocess": ok and pre_len == 0,
                    "error": error,
                    "first_200_chars": preprocessed[:200],
                }
            )

        # 통계
        valid = [r for r in results if r["ok"] and r["preprocessed_length"] > 0]
        if valid:
            lens = sorted(r["preprocessed_length"] for r in valid)
            n = len(lens)
            min_len = lens[0]
            max_len = lens[-1]
            median_len = lens[n // 2]
            avg_len = sum(lens) // n
            shortest = min(valid, key=lambda r: r["preprocessed_length"])
            longest = max(valid, key=lambda r: r["preprocessed_length"])
        else:
            min_len = max_len = median_len = avg_len = 0
            shortest = longest = None

        payload = {
            "input": str(in_path),
            "summary": {
                "count": len(downloaded),
                "succeeded": succeeded,
                "failed": failed,
                "empty_after_preprocess": empty_after_preprocess,
                "total_seconds": round(total_seconds, 2),
                "avg_seconds_per_file": (
                    round(total_seconds / len(downloaded), 3) if downloaded else 0
                ),
                "preprocessed_length_min": min_len,
                "preprocessed_length_max": max_len,
                "preprocessed_length_median": median_len,
                "preprocessed_length_avg": avg_len,
                "shortest_file": shortest["file_name"] if shortest else None,
                "longest_file": longest["file_name"] if longest else None,
            },
            "results": results,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Summary ==="))
        for k, v in payload["summary"].items():
            self.stdout.write(f"  {k}: {v}")
        self.stdout.write("")
        self.stdout.write(f"Saved: {out_path}")
        self.stdout.write(f"Texts: {text_dir}/")
