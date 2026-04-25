"""Step B3.5 — 추출된 텍스트에서 출생년도 추출 + cutoff 필터.

LLM 호출 전에 cutoff(예: 1980)에 미달하는 후보자를 스킵해서 비용·시간을 절감.

Usage:
    uv run python manage.py verify_birth_filter \\
        --input snapshots/step_b2_text_v2.json \\
        --cutoff 1980 \\
        --output snapshots/step_b3_5_birth_filter.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from data_extraction.services.text import (
    normalize_birth_year_filter_value,
    passes_birth_year_filter,
)


class Command(BaseCommand):
    help = "Step B3.5: filter extracted texts by detected birth year."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True)
        parser.add_argument(
            "--cutoff",
            type=int,
            required=True,
            help="4자리 출생년도 (예: 1980 → 1980년 이후 출생자만 통과) "
            "또는 2자리 나이 (예: 45 → 만 45세 이하 통과)",
        )
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        in_path = Path(options["input"])
        out_path = Path(options["output"])
        cutoff_value = options["cutoff"]
        cutoff_year = normalize_birth_year_filter_value(cutoff_value)

        spec = json.loads(in_path.read_text(encoding="utf-8"))
        results_in = [r for r in spec.get("results", []) if r.get("ok") and r.get("text_path")]

        results_out = []
        passed = 0
        skipped = 0
        no_year = 0

        self.stdout.write(
            f"Cutoff: {cutoff_year} (input={cutoff_value}). "
            f"검사 대상: {len(results_in)}건"
        )
        self.stdout.write("")

        for r in results_in:
            text = Path(r["text_path"]).read_text(encoding="utf-8")
            outcome = passes_birth_year_filter(
                text,
                cutoff_year,
                enabled=True,
                file_name=r.get("file_name"),
            )
            if outcome.passed:
                passed += 1
                verdict = "PASS"
            else:
                skipped += 1
                verdict = "SKIP"
            if outcome.detected_year is None:
                no_year += 1

            year_str = (
                f"{outcome.detected_year}" if outcome.detected_year else "?"
            )
            evidence = (outcome.evidence or "")[:30]
            line = (
                f"  [{r['category']:<12}] {verdict}  "
                f"birth={year_str:<5} src={outcome.source:<25} "
                f"ev={evidence:<30} "
                f"{r['file_name'][:35]}"
            )
            if not outcome.passed:
                line += f"  ← {outcome.reason}"
            self.stdout.write(line)

            results_out.append(
                {
                    "category": r["category"],
                    "file_id": r["file_id"],
                    "file_name": r["file_name"],
                    "text_path": r["text_path"],
                    "passed": outcome.passed,
                    "detected_year": outcome.detected_year,
                    "cutoff_year": outcome.cutoff_year,
                    "source": outcome.source,
                    "evidence": outcome.evidence,
                    "reason": outcome.reason,
                }
            )

        payload = {
            "input": str(in_path),
            "cutoff_year": cutoff_year,
            "summary": {
                "total": len(results_in),
                "passed": passed,
                "skipped": skipped,
                "no_year_detected": no_year,
                "skip_pct": round(100.0 * skipped / len(results_in), 1)
                if results_in
                else 0,
            },
            "results": results_out,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
