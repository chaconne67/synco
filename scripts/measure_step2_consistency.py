"""Step 2 일관성 측정 — 동일 raw careers를 N회 normalize 후 통합 결과 비교.

Usage:
    DJANGO_SETTINGS_MODULE=main.settings uv run python scripts/measure_step2_consistency.py \
        --b4-json snapshots/step_b4_llm_step1/<file_id>.json \
        --iterations 5 \
        --label kang_min_joo
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
django.setup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--b4-json", required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--output-dir",
        default="snapshots/consistency",
    )
    args = parser.parse_args()

    from data_extraction.services.extraction.integrity import (
        normalize_career_group,
        normalize_education_group,
    )

    b4 = json.loads(Path(args.b4_json).read_text(encoding="utf-8"))
    raw_careers = b4["result"].get("careers") or []
    raw_educations = b4["result"].get("educations") or []
    fname = b4.get("file_name") or args.b4_json
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"=== Step 2 consistency: {fname} × {args.iterations} ==="
    )
    print(f"  raw careers: {len(raw_careers)} / raw educations: {len(raw_educations)}")
    print()

    runs = []
    for i in range(args.iterations):
        t0 = time.time()
        try:
            cr = normalize_career_group(raw_careers, "전체 경력")
        except Exception as exc:
            print(f"  [{i+1}/{args.iterations}] career FAIL: {exc}")
            runs.append({"iteration": i + 1, "error": f"career: {exc}"})
            continue
        try:
            er = normalize_education_group(raw_educations)
        except Exception as exc:
            print(f"  [{i+1}/{args.iterations}] edu FAIL: {exc}")
            runs.append({"iteration": i + 1, "error": f"edu: {exc}"})
            continue
        elapsed = time.time() - t0

        cars = cr.get("careers") or []
        edus = er.get("educations") or []
        car_summary = " | ".join(
            f"{(c.get('company') or '')[:25]}({c.get('start_date')}~{c.get('end_date')})"
            for c in cars
        )
        cflags = cr.get("flags") or []
        eflags = er.get("flags") or []
        red_count = sum(
            1
            for f in cflags + eflags
            if f.get("severity") == "RED"
        )
        yel_count = sum(
            1
            for f in cflags + eflags
            if f.get("severity") == "YELLOW"
        )
        print(
            f"  [{i+1}/{args.iterations}] {elapsed:.1f}s "
            f"car={len(raw_careers)}→{len(cars)} edu={len(raw_educations)}→{len(edus)} "
            f"R{red_count}/Y{yel_count}"
        )
        print(f"      careers: {car_summary}")
        runs.append(
            {
                "iteration": i + 1,
                "elapsed_s": round(elapsed, 2),
                "career_result": cr,
                "edu_result": er,
            }
        )

    out_path = out_dir / f"step2_{args.label}.json"
    out_path.write_text(
        json.dumps(
            {
                "b4_json": args.b4_json,
                "file_name": fname,
                "iterations": args.iterations,
                "raw_careers_count": len(raw_careers),
                "raw_educations_count": len(raw_educations),
                "runs": runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print()
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
