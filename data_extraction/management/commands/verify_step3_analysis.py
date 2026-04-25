"""Step B7 — Step 2 정규화 결과에 Step 3 코드 분석 적용.

LLM 호출 없음. 순수 코드 분석 5종:
  1. check_period_overlaps         경력 기간 중복 (동시 근무 의심)
  2. check_career_education_overlap 정규직과 재학 기간 중복
  3. check_education_gaps          학력 갭 (입학년도 누락, 학사 누락)
  4. check_campus_match            멀티캠퍼스 대학 캠퍼스 정보
  5. (compare_versions은 이전 데이터 있을 때만 — 첫 추출이라 skip)

Usage:
    uv run python manage.py verify_step3_analysis \\
        --input-dir snapshots/step_b5_llm_step2 \\
        --output-dir snapshots/step_b7_step3 \\
        --summary-output snapshots/step_b7_summary.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Step B7: code-only Step 3 analysis on normalized careers/educations."

    def add_arguments(self, parser):
        parser.add_argument("--input-dir", type=str, required=True)
        parser.add_argument("--output-dir", type=str, required=True)
        parser.add_argument("--summary-output", type=str, required=True)

    def handle(self, *args, **options):
        from data_extraction.services.extraction.integrity import (
            check_period_overlaps,
            check_career_education_overlap,
            check_education_gaps,
            check_campus_match,
        )

        in_dir = Path(options["input_dir"])
        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(in_dir.glob("*.json"))
        summary = []
        agg = {
            "period_overlap": 0,
            "career_education_overlap": 0,
            "education_gap": 0,
            "campus_match": 0,
            "campus_missing": 0,
        }
        red_total = 0
        yellow_total = 0

        self.stdout.write(f"Running Step 3 analysis on {len(files)} candidates")
        self.stdout.write("")

        for idx, f in enumerate(files, start=1):
            data = json.loads(f.read_text(encoding="utf-8"))
            target = data.get("target") or {}
            step2 = data.get("step2") or {}
            careers = ((step2.get("career_result") or {}).get("careers")) or []
            educations = ((step2.get("edu_result") or {}).get("educations")) or []

            period_flags = check_period_overlaps(careers)
            ce_flags = check_career_education_overlap(careers, educations)
            edu_gap_flags = check_education_gaps(educations)
            campus_flags = check_campus_match(educations)

            all_flags = period_flags + ce_flags + edu_gap_flags + campus_flags
            red = sum(1 for fl in all_flags if fl.get("severity") == "RED")
            yellow = sum(1 for fl in all_flags if fl.get("severity") == "YELLOW")
            red_total += red
            yellow_total += yellow

            for fl in period_flags: agg["period_overlap"] += 1
            for fl in ce_flags: agg["career_education_overlap"] += 1
            for fl in edu_gap_flags: agg["education_gap"] += 1
            for fl in campus_flags:
                if fl.get("type") == "CAMPUS_DEPARTMENT_MATCH":
                    agg["campus_match"] += 1
                else:
                    agg["campus_missing"] += 1

            verdict = "clean" if not all_flags else f"R{red}/Y{yellow}"
            self.stdout.write(
                f"  [{idx:>2}/{len(files)}] [{target.get('category'):<12}] "
                f"{verdict:<10} "
                f"period={len(period_flags)} ce={len(ce_flags)} "
                f"edu_gap={len(edu_gap_flags)} campus={len(campus_flags)}  "
                f"{target.get('file_name')[:35]}"
            )

            if all_flags:
                for fl in all_flags:
                    self.stdout.write(
                        f"      [{fl.get('severity')}] {fl.get('type')}: {fl.get('detail','')[:120]}"
                    )

            payload = {
                "target": target,
                "step3_flags": {
                    "period_overlap": period_flags,
                    "career_education_overlap": ce_flags,
                    "education_gap": edu_gap_flags,
                    "campus_match": campus_flags,
                },
                "totals": {"red": red, "yellow": yellow},
            }
            (out_dir / f.name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary.append({
                "category": target.get("category"),
                "file_name": target.get("file_name"),
                "file_id": target.get("file_id"),
                "period_overlap": len(period_flags),
                "career_education_overlap": len(ce_flags),
                "education_gap": len(edu_gap_flags),
                "campus_match": sum(1 for fl in campus_flags if fl.get("type") == "CAMPUS_DEPARTMENT_MATCH"),
                "campus_missing": sum(1 for fl in campus_flags if fl.get("type") != "CAMPUS_DEPARTMENT_MATCH"),
                "red": red,
                "yellow": yellow,
            })

        result = {
            "summary": {
                "files": len(files),
                "total_red": red_total,
                "total_yellow": yellow_total,
                "by_check": agg,
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
        self.stdout.write(f"  files: {len(files)}")
        self.stdout.write(f"  total_red: {red_total}")
        self.stdout.write(f"  total_yellow: {yellow_total}")
        self.stdout.write(f"  by_check:")
        for k, v in agg.items():
            self.stdout.write(f"    {k}: {v}")
        self.stdout.write("")
        self.stdout.write(f"Per-file: {out_dir}/")
        self.stdout.write(f"Summary:  {options['summary_output']}")
