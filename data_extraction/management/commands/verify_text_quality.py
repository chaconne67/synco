"""Step B3 — 전처리된 텍스트의 품질 분류.

LLM 호출 직전 마지막 게이트. ok / too_short / garbled / empty 분기.
fail 분기에 해당하면 LLM 호출 없이 placeholder로 저장됨.

Usage:
    uv run python manage.py verify_text_quality \\
        --input snapshots/step_b2_text_v5.json \\
        --output snapshots/step_b3_quality.json
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from data_extraction.services.text import classify_text_quality


class Command(BaseCommand):
    help = "Step B3: classify preprocessed text quality."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True)
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        in_path = Path(options["input"])
        out_path = Path(options["output"])
        spec = json.loads(in_path.read_text(encoding="utf-8"))
        results_in = [r for r in spec.get("results", []) if r.get("ok")]

        verdicts = Counter()
        results_out = []

        self.stdout.write(f"Classifying {len(results_in)} preprocessed texts")
        self.stdout.write("")

        for r in results_in:
            text_path = r.get("text_path")
            if text_path and Path(text_path).exists():
                text = Path(text_path).read_text(encoding="utf-8")
            else:
                text = ""
            verdict = classify_text_quality(text)
            verdicts[verdict] += 1

            stripped = text.strip()
            alnum = sum(
                1 for c in stripped if c.isalnum() or "가" <= c <= "힣"
            )
            alnum_ratio = alnum / len(stripped) if stripped else 0

            line = (
                f"  [{r['category']:<12}] {verdict:<10} "
                f"len={len(text):>6d} "
                f"alnum={alnum_ratio*100:>4.0f}%   "
                f"{r['file_name'][:50]}"
            )
            self.stdout.write(line)

            results_out.append(
                {
                    "category": r["category"],
                    "file_id": r["file_id"],
                    "file_name": r["file_name"],
                    "text_path": text_path,
                    "preprocessed_length": len(text),
                    "alnum_ratio": round(alnum_ratio, 3),
                    "verdict": verdict,
                    "would_skip_llm": verdict != "ok",
                }
            )

        payload = {
            "input": str(in_path),
            "summary": {
                "total": len(results_in),
                "verdicts": dict(verdicts),
                "ok_pct": round(100 * verdicts["ok"] / len(results_in), 1)
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
        for k, v in verdicts.items():
            self.stdout.write(f"  {k}: {v}")
        self.stdout.write(f"  ok %: {payload['summary']['ok_pct']}")
        self.stdout.write("")
        self.stdout.write(f"Saved: {out_path}")
