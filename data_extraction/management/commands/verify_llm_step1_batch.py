"""Step B4 batch — birth filter PASS 케이스 모두에 대해 Step 1 LLM 호출.

Usage:
    uv run python manage.py verify_llm_step1_batch \\
        --input snapshots/step_b3_quality.json \\
        --filter-pass-from snapshots/step_b3_5_birth_filter_v4.json \\
        --output-dir snapshots/step_b4_llm_step1 \\
        --summary-output snapshots/step_b4_llm_step1_summary.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Step B4 batch: invoke LLM Step 1 on each birth-filter-PASS resume."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True)
        parser.add_argument(
            "--filter-pass-from",
            type=str,
            default="",
            help="snapshots/step_b3_5_birth_filter_*.json — passed=true만 처리",
        )
        parser.add_argument("--output-dir", type=str, required=True)
        parser.add_argument("--summary-output", type=str, required=True)
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="output-dir에 이미 결과 JSON이 있으면 스킵 (재실행용)",
        )

    def handle(self, *args, **options):
        from data_extraction.services.extraction import telemetry
        from data_extraction.services.extraction.integrity import extract_raw_data

        in_path = Path(options["input"])
        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        spec = json.loads(in_path.read_text(encoding="utf-8"))
        records = spec.get("results", [])

        # birth filter pass 적용
        if options["filter_pass_from"]:
            bf = json.loads(Path(options["filter_pass_from"]).read_text(encoding="utf-8"))
            pass_ids = {r["file_id"] for r in bf["results"] if r.get("passed")}
            records = [r for r in records if r["file_id"] in pass_ids]
            self.stdout.write(
                f"birth filter PASS only: {len(records)}건 처리 대상"
            )

        summary = []
        succeeded = 0
        failed = 0
        total_in_tokens = 0
        total_out_tokens = 0
        total_seconds = 0.0
        skipped_existing = 0

        for idx, r in enumerate(records, start=1):
            out_path = out_dir / f"{r['file_id']}.json"
            if options["skip_existing"] and out_path.exists():
                skipped_existing += 1
                self.stdout.write(
                    f"  [{idx:>2}/{len(records)}] [{r['category']:<12}] SKIP (existing) {r['file_name'][:40]}"
                )
                continue

            text = Path(r["text_path"]).read_text(encoding="utf-8")

            telemetry.reset()
            t0 = time.time()
            error = ""
            extracted = None
            try:
                extracted = extract_raw_data(text, file_name=r["file_name"])
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.time() - t0
            tokens = telemetry.snapshot()

            ok = extracted is not None
            total_in_tokens += tokens["input_tokens"]
            total_out_tokens += tokens["output_tokens"]
            total_seconds += elapsed
            if ok:
                succeeded += 1
            else:
                failed += 1

            entry = {
                "category": r["category"],
                "file_id": r["file_id"],
                "file_name": r["file_name"],
                "text_path": r["text_path"],
                "preprocessed_length": r["preprocessed_length"],
                "elapsed_seconds": round(elapsed, 2),
                "token_usage": tokens,
                "ok": ok,
                "error": error,
            }
            payload = {**entry, "result": extracted}
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            verdict = "OK  " if ok else "FAIL"
            careers_n = len(extracted.get("careers") or []) if extracted else 0
            edus_n = len(extracted.get("educations") or []) if extracted else 0
            self.stdout.write(
                f"  [{idx:>2}/{len(records)}] [{r['category']:<12}] {verdict} "
                f"{elapsed:>5.1f}s in={tokens['input_tokens']:>5} out={tokens['output_tokens']:>5} "
                f"calls={tokens['calls']} "
                f"careers={careers_n} edus={edus_n}  {r['file_name'][:35]}"
                + (f"  ← {error[:60]}" if error else "")
            )
            summary.append({**entry})

        # cost
        cost_usd = (
            total_in_tokens / 1_000_000 * 0.10
            + total_out_tokens / 1_000_000 * 0.40
        )
        result = {
            "input": str(in_path),
            "summary": {
                "processed": len(records) - skipped_existing,
                "succeeded": succeeded,
                "failed": failed,
                "skipped_existing": skipped_existing,
                "total_seconds": round(total_seconds, 1),
                "total_input_tokens": total_in_tokens,
                "total_output_tokens": total_out_tokens,
                "cost_usd": round(cost_usd, 4),
                "cost_krw": round(cost_usd * 1380, 0),
            },
            "results": summary,
        }
        Path(options["summary_output"]).parent.mkdir(parents=True, exist_ok=True)
        Path(options["summary_output"]).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Summary ==="))
        for k, v in result["summary"].items():
            self.stdout.write(f"  {k}: {v}")
        self.stdout.write("")
        self.stdout.write(f"Per-file: {out_dir}/")
        self.stdout.write(f"Summary: {options['summary_output']}")
