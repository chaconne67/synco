"""Step 1 일관성 측정 — 동일 텍스트 N회 추출 후 institution/degree/company 표기 비교.

Usage:
    DJANGO_SETTINGS_MODULE=main.settings uv run python scripts/measure_step1_consistency.py \
        --file-id 1aWi-nT-aaZF6l7yTGBjP4-kT-teveCxI \
        --text-path logs/extraction-test/b2_text/1aWi-nT-aaZF6l7yTGBjP4-kT-teveCxI.txt \
        --file-name "강신호영문이력서.doc" \
        --iterations 5 \
        --label kang
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
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--text-path", required=True)
    parser.add_argument("--file-name", required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--label", required=True, help="결과 파일 prefix")
    parser.add_argument(
        "--output-dir",
        default="snapshots/consistency",
        help="결과 저장 디렉토리",
    )
    args = parser.parse_args()

    from data_extraction.services.extraction.integrity import extract_raw_data

    text = Path(args.text_path).read_text(encoding="utf-8")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Step 1 consistency: {args.file_name} × {args.iterations} ===")
    runs = []
    for i in range(args.iterations):
        t0 = time.time()
        try:
            extracted = extract_raw_data(text, file_name=args.file_name)
        except Exception as exc:
            print(f"  [{i+1}/{args.iterations}] FAIL {exc}")
            runs.append({"iteration": i + 1, "error": str(exc)})
            continue
        elapsed = time.time() - t0
        if extracted is None:
            print(f"  [{i+1}/{args.iterations}] None (3 retries failed)")
            runs.append({"iteration": i + 1, "error": "None"})
            continue
        runs.append(
            {
                "iteration": i + 1,
                "elapsed_s": round(elapsed, 2),
                "result": extracted,
            }
        )
        # 즉석 요약
        edus = extracted.get("educations") or []
        cars = extracted.get("careers") or []
        edu_summary = " | ".join(
            f"{(e.get('institution') or '')[:30]}/{e.get('degree')}"
            for e in edus
        )
        print(
            f"  [{i+1}/{args.iterations}] {elapsed:.1f}s "
            f"careers={len(cars)} edus={len(edus)}  edu: {edu_summary}"
        )

    out_path = out_dir / f"step1_{args.label}.json"
    out_path.write_text(
        json.dumps(
            {
                "file_id": args.file_id,
                "file_name": args.file_name,
                "iterations": args.iterations,
                "runs": runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
