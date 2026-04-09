"""Compare Gemini vs OpenAI GPT-5.4 Nano extraction quality.

Usage:
    DJANGO_SETTINGS_MODULE=main.settings uv run python scripts/compare_providers.py
"""

import json
import os
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from candidates.models import Candidate, Resume
from data_extraction.services.extraction.openai import extract_candidate_data


def compare_field(gemini_val, openai_val):
    """Compare two field values. Returns: match, gemini_present, openai_present."""
    g = (
        bool(gemini_val)
        if not isinstance(gemini_val, (int, float))
        else gemini_val is not None
    )
    o = (
        bool(openai_val)
        if not isinstance(openai_val, (int, float))
        else openai_val is not None
    )
    match = False
    if g and o:
        if isinstance(gemini_val, str) and isinstance(openai_val, str):
            match = gemini_val.strip() == openai_val.strip()
        else:
            match = gemini_val == openai_val
    elif not g and not o:
        match = True
    return match, g, o


def count_items(data, key):
    """Count items in a list field."""
    val = data.get(key, [])
    if isinstance(val, list):
        return len(val)
    return 0


def run():
    candidates = Candidate.objects.prefetch_related("careers", "educations").all()

    results = []
    total_time = 0
    total_input_tokens = 0
    total_output_tokens = 0
    errors = 0

    print(f"\n{'=' * 70}")
    print(
        f"  Gemini vs GPT-5.4 Nano Extraction Comparison ({candidates.count()} candidates)"
    )
    print(f"{'=' * 70}\n")

    for i, c in enumerate(candidates):
        resume = (
            Resume.objects.filter(candidate=c, raw_text__isnull=False)
            .exclude(raw_text="")
            .first()
        )
        if not resume:
            print(f"  [{i + 1:2d}] {c.name} — no raw_text, skipping")
            continue

        raw_text = resume.raw_text
        gemini_data = c.raw_extracted_json or {}

        # Extract with OpenAI
        t0 = time.time()
        openai_data = extract_candidate_data(raw_text, max_retries=2)
        elapsed = time.time() - t0
        total_time += elapsed

        if not openai_data:
            errors += 1
            print(f"  [{i + 1:2d}] {c.name} — OpenAI FAILED ({elapsed:.1f}s)")
            results.append({"name": c.name, "status": "error"})
            continue

        # Compare scalar fields
        scalar_fields = ["name", "birth_year", "email", "phone"]
        field_results = {}
        for f in scalar_fields:
            g_val = gemini_data.get(f) or getattr(c, f, None)
            o_val = openai_data.get(f)
            match, g_present, o_present = compare_field(g_val, o_val)
            field_results[f] = {
                "gemini": g_val,
                "openai": o_val,
                "match": match,
                "g_present": g_present,
                "o_present": o_present,
            }

        # Compare list counts
        list_fields = [
            "careers",
            "educations",
            "skills",
            "certifications",
            "language_skills",
        ]
        count_results = {}
        for f in list_fields:
            g_count = (
                count_items(gemini_data, f) if gemini_data else getattr(c, f"{f}", None)
            )
            if g_count is None or isinstance(g_count, list):
                # fallback to DB relation count
                if f == "careers":
                    g_count = c.careers.count()
                elif f == "educations":
                    g_count = c.educations.count()
                elif f == "certifications":
                    g_count = c.certifications.count()
                elif f == "language_skills":
                    g_count = c.language_skills.count()
                elif f == "skills":
                    g_count = len(c.skills) if isinstance(c.skills, list) else 0
            o_count = count_items(openai_data, f)
            count_results[f] = {"gemini": g_count, "openai": o_count}

        # Quality: field completeness
        openai_filled = sum(1 for f in scalar_fields if field_results[f]["o_present"])
        gemini_filled = sum(1 for f in scalar_fields if field_results[f]["g_present"])
        matches = sum(1 for f in scalar_fields if field_results[f]["match"])

        status_icon = "✓" if matches == len(scalar_fields) else "△"
        mismatch_fields = [f for f in scalar_fields if not field_results[f]["match"]]
        mismatch_info = ""
        if mismatch_fields:
            parts = []
            for f in mismatch_fields:
                fr = field_results[f]
                parts.append(f"{f}: G={fr['gemini']} vs O={fr['openai']}")
            mismatch_info = f"  diff: {'; '.join(parts)}"

        print(
            f"  [{i + 1:2d}] {c.name:8s} {status_icon}  {elapsed:.1f}s  "
            f"careers={count_results['careers']['gemini']}→{count_results['careers']['openai']}  "
            f"edu={count_results['educations']['gemini']}→{count_results['educations']['openai']}  "
            f"skills={count_results['skills']['gemini']}→{count_results['skills']['openai']}"
            f"{mismatch_info}"
        )

        results.append(
            {
                "name": c.name,
                "status": "ok",
                "time": elapsed,
                "scalar_matches": matches,
                "scalar_total": len(scalar_fields),
                "field_results": field_results,
                "count_results": count_results,
                "openai_filled": openai_filled,
                "gemini_filled": gemini_filled,
            }
        )

    # Summary
    ok_results = [r for r in results if r["status"] == "ok"]
    if not ok_results:
        print("\nNo successful extractions to compare.")
        return

    avg_time = total_time / len(ok_results)
    total_matches = sum(r["scalar_matches"] for r in ok_results)
    total_scalars = sum(r["scalar_total"] for r in ok_results)
    scalar_accuracy = total_matches / total_scalars * 100 if total_scalars else 0

    # Count comparisons
    more_careers = sum(
        1
        for r in ok_results
        if r["count_results"]["careers"]["openai"]
        > r["count_results"]["careers"]["gemini"]
    )
    fewer_careers = sum(
        1
        for r in ok_results
        if r["count_results"]["careers"]["openai"]
        < r["count_results"]["careers"]["gemini"]
    )
    equal_careers = sum(
        1
        for r in ok_results
        if r["count_results"]["careers"]["openai"]
        == r["count_results"]["careers"]["gemini"]
    )

    more_edu = sum(
        1
        for r in ok_results
        if r["count_results"]["educations"]["openai"]
        > r["count_results"]["educations"]["gemini"]
    )
    fewer_edu = sum(
        1
        for r in ok_results
        if r["count_results"]["educations"]["openai"]
        < r["count_results"]["educations"]["gemini"]
    )
    equal_edu = sum(
        1
        for r in ok_results
        if r["count_results"]["educations"]["openai"]
        == r["count_results"]["educations"]["gemini"]
    )

    more_skills = sum(
        1
        for r in ok_results
        if r["count_results"]["skills"]["openai"]
        > r["count_results"]["skills"]["gemini"]
    )
    fewer_skills = sum(
        1
        for r in ok_results
        if r["count_results"]["skills"]["openai"]
        < r["count_results"]["skills"]["gemini"]
    )
    equal_skills = sum(
        1
        for r in ok_results
        if r["count_results"]["skills"]["openai"]
        == r["count_results"]["skills"]["gemini"]
    )

    # Cost estimate: GPT-5.4 Nano pricing (input: $0.10/1M, output: $0.40/1M tokens approx)
    # Rough estimate: ~1500 input tokens, ~800 output tokens per resume
    est_input_cost = len(ok_results) * 1500 * 0.10 / 1_000_000
    est_output_cost = len(ok_results) * 800 * 0.40 / 1_000_000
    est_total_cost = est_input_cost + est_output_cost

    # Gemini Flash Lite pricing: $0.0375/1M input, $0.15/1M output
    gemini_input_cost = len(ok_results) * 1500 * 0.0375 / 1_000_000
    gemini_output_cost = len(ok_results) * 800 * 0.15 / 1_000_000
    gemini_total_cost = gemini_input_cost + gemini_output_cost

    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n  [Time]")
    print(f"    Total:   {total_time:.1f}s")
    print(f"    Average: {avg_time:.1f}s per resume")
    print(f"    Errors:  {errors}/{len(results)}")

    print(f"\n  [Cost estimate per 40 resumes]")
    print(f"    Gemini 3.1 Flash Lite: ~${gemini_total_cost:.4f}")
    print(f"    GPT-5.4 Nano:         ~${est_total_cost:.4f}")
    print(
        f"    Ratio:                 {est_total_cost / gemini_total_cost:.1f}x"
        if gemini_total_cost > 0
        else ""
    )

    print(f"\n  [Quality — Scalar field agreement (name, birth_year, email, phone)]")
    print(f"    Match rate: {scalar_accuracy:.1f}% ({total_matches}/{total_scalars})")

    # Per-field breakdown
    for f in ["name", "birth_year", "email", "phone"]:
        f_match = sum(1 for r in ok_results if r["field_results"][f]["match"])
        f_g = sum(1 for r in ok_results if r["field_results"][f]["g_present"])
        f_o = sum(1 for r in ok_results if r["field_results"][f]["o_present"])
        print(
            f"    {f:12s}: match={f_match}/{len(ok_results)}  gemini={f_g}  openai={f_o}"
        )

    print(f"\n  [Quality — List field counts (OpenAI vs Gemini)]")
    print(
        f"    careers:    equal={equal_careers}  more={more_careers}  fewer={fewer_careers}"
    )
    print(f"    educations: equal={equal_edu}  more={more_edu}  fewer={fewer_edu}")
    print(
        f"    skills:     equal={equal_skills}  more={more_skills}  fewer={fewer_skills}"
    )

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    run()
