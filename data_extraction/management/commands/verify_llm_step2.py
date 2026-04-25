"""Step B5 — Step 1 결과를 입력으로 Step 2 (career + education) 정규화 호출.

각 후보자마다 2 호출 (career, education).

Usage:
    uv run python manage.py verify_llm_step2 \\
        --input-dir snapshots/step_b4_llm_step1 \\
        --output-dir snapshots/step_b5_llm_step2 \\
        --summary-output snapshots/step_b5_summary.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Step B5: invoke Step 2 (career + education normalization) on each candidate."

    def add_arguments(self, parser):
        parser.add_argument("--input-dir", type=str, required=True)
        parser.add_argument("--output-dir", type=str, required=True)
        parser.add_argument("--summary-output", type=str, required=True)

    def handle(self, *args, **options):
        from data_extraction.services.extraction import telemetry
        from data_extraction.services.extraction.integrity import (
            normalize_career_group,
            normalize_education_group,
        )

        in_dir = Path(options["input_dir"])
        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        summary = []
        total_in = 0
        total_out = 0
        total_calls = 0
        total_seconds = 0.0
        succeeded_career = 0
        failed_career = 0
        succeeded_edu = 0
        failed_edu = 0

        files = sorted(in_dir.glob("*.json"))
        self.stdout.write(f"Step 2 호출: {len(files)}건 × 2 (career + education)")
        self.stdout.write("")

        for idx, f in enumerate(files, start=1):
            data = json.loads(f.read_text(encoding="utf-8"))
            target = data.get("target") or data
            extracted = data.get("result") or {}
            raw_careers = extracted.get("careers") or []
            raw_educations = extracted.get("educations") or []

            telemetry.reset()
            t0 = time.time()
            try:
                career_result = normalize_career_group(raw_careers, "전체 경력")
                career_ok = career_result is not None
            except Exception as exc:
                career_result = None
                career_ok = False
            t_career = time.time() - t0

            t1 = time.time()
            try:
                edu_result = normalize_education_group(raw_educations)
                edu_ok = edu_result is not None
            except Exception as exc:
                edu_result = None
                edu_ok = False
            t_edu = time.time() - t1

            tokens = telemetry.snapshot()
            elapsed = t_career + t_edu
            total_in += tokens["input_tokens"]
            total_out += tokens["output_tokens"]
            total_calls += tokens["calls"]
            total_seconds += elapsed
            if career_ok: succeeded_career += 1
            else: failed_career += 1
            if edu_ok: succeeded_edu += 1
            else: failed_edu += 1

            careers_norm = (career_result or {}).get("careers") or []
            edus_norm = (edu_result or {}).get("educations") or []
            career_flags = (career_result or {}).get("flags") or []
            edu_flags = (edu_result or {}).get("flags") or []
            red_flags = sum(1 for f in career_flags + edu_flags if f.get("severity") == "RED")
            yellow_flags = sum(1 for f in career_flags + edu_flags if f.get("severity") == "YELLOW")

            verdict_c = "OK" if career_ok else "FAIL"
            verdict_e = "OK" if edu_ok else "FAIL"
            self.stdout.write(
                f"  [{idx:>2}/{len(files)}] [{target.get('category'):<12}] "
                f"car({verdict_c}) {len(raw_careers)}→{len(careers_norm)} "
                f"edu({verdict_e}) {len(raw_educations)}→{len(edus_norm)} "
                f"flags(R{red_flags}/Y{yellow_flags}) "
                f"{elapsed:>5.1f}s in={tokens['input_tokens']:>5} out={tokens['output_tokens']:>5}  "
                f"{target.get('file_name')[:30]}"
            )

            payload = {
                "target": target,
                "raw": {
                    "careers": raw_careers,
                    "educations": raw_educations,
                },
                "step2": {
                    "career_result": career_result,
                    "edu_result": edu_result,
                },
                "elapsed_seconds": round(elapsed, 2),
                "token_usage": tokens,
            }
            (out_dir / f.name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary.append({
                "category": target.get("category"),
                "file_name": target.get("file_name"),
                "file_id": target.get("file_id"),
                "raw_careers_n": len(raw_careers),
                "norm_careers_n": len(careers_norm),
                "raw_educations_n": len(raw_educations),
                "norm_educations_n": len(edus_norm),
                "career_red": sum(1 for f in career_flags if f.get("severity") == "RED"),
                "career_yellow": sum(1 for f in career_flags if f.get("severity") == "YELLOW"),
                "edu_red": sum(1 for f in edu_flags if f.get("severity") == "RED"),
                "edu_yellow": sum(1 for f in edu_flags if f.get("severity") == "YELLOW"),
                "elapsed": round(elapsed, 2),
                "tokens": tokens,
                "career_ok": career_ok,
                "edu_ok": edu_ok,
            })

        cost_usd = (total_in / 1_000_000 * 0.10) + (total_out / 1_000_000 * 0.40)
        result = {
            "summary": {
                "files": len(files),
                "career_succeeded": succeeded_career,
                "career_failed": failed_career,
                "edu_succeeded": succeeded_edu,
                "edu_failed": failed_edu,
                "total_calls": total_calls,
                "total_seconds": round(total_seconds, 1),
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
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
        self.stdout.write(f"Summary:  {options['summary_output']}")
