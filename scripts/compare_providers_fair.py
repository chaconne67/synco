"""Fair comparison: Gemini vs GPT-5.4 Nano through identical pipeline.

Same input (preprocessed raw_text), same postprocessing (apply_regex_field_filters),
same validation — only the LLM model differs.

Usage:
    DJANGO_SETTINGS_MODULE=main.settings uv run python scripts/compare_providers_fair.py
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
from data_extraction.services.extraction.gemini import (
    extract_candidate_data as gemini_extract,
)
from data_extraction.services.extraction.openai import (
    extract_candidate_data as openai_extract,
)
from data_extraction.services.filters import apply_regex_field_filters

LIMIT = 20


def safe_get(d, key, default=None):
    if not d:
        return default
    return d.get(key, default)


def count_list(d, key):
    v = safe_get(d, key, [])
    return len(v) if isinstance(v, list) else 0


def normalize_str(v):
    if not v:
        return ""
    return str(v).strip().lower().replace(" ", "")


def field_match(g, o):
    return normalize_str(g) == normalize_str(o)


def run():
    resumes = (
        Resume.objects.filter(raw_text__isnull=False, candidate__isnull=False)
        .exclude(raw_text="")
        .select_related("candidate")
        .order_by("candidate__name")[:LIMIT]
    )

    print(f"\n{'=' * 80}")
    print(
        f"  Fair Comparison: Gemini 3.1 Flash Lite vs GPT-5.4 Nano ({len(resumes)} resumes)"
    )
    print(f"  Pipeline: raw_text → LLM extract → apply_regex_field_filters → compare")
    print(f"{'=' * 80}\n")

    scalar_fields = ["name", "birth_year", "email", "phone"]
    list_fields = [
        "careers",
        "educations",
        "skills",
        "certifications",
        "language_skills",
    ]

    totals = {
        "gemini_time": 0,
        "openai_time": 0,
        "gemini_fail": 0,
        "openai_fail": 0,
        "field_match": {f: 0 for f in scalar_fields},
        "field_both_present": {f: 0 for f in scalar_fields},
        "gemini_filled": {f: 0 for f in scalar_fields},
        "openai_filled": {f: 0 for f in scalar_fields},
        "list_gemini": {f: 0 for f in list_fields},
        "list_openai": {f: 0 for f in list_fields},
        "ok_count": 0,
    }

    for i, resume in enumerate(resumes):
        c = resume.candidate
        raw_text = resume.raw_text

        # --- Gemini ---
        t0 = time.time()
        g_raw = gemini_extract(raw_text, max_retries=2)
        g_time = time.time() - t0
        g = apply_regex_field_filters(g_raw) if g_raw else None
        totals["gemini_time"] += g_time

        # --- OpenAI ---
        t1 = time.time()
        o_raw = openai_extract(raw_text, max_retries=2)
        o_time = time.time() - t1
        o = apply_regex_field_filters(o_raw) if o_raw else None
        totals["openai_time"] += o_time

        if not g:
            totals["gemini_fail"] += 1
        if not o:
            totals["openai_fail"] += 1

        if not g and not o:
            print(
                f"  [{i + 1:2d}] {c.name:8s}  BOTH FAILED  G={g_time:.1f}s  O={o_time:.1f}s"
            )
            continue
        if not g:
            print(
                f"  [{i + 1:2d}] {c.name:8s}  GEMINI FAIL  G={g_time:.1f}s  O={o_time:.1f}s"
            )
            continue
        if not o:
            print(
                f"  [{i + 1:2d}] {c.name:8s}  OPENAI FAIL  G={g_time:.1f}s  O={o_time:.1f}s"
            )
            continue

        totals["ok_count"] += 1

        # Scalar comparison
        diffs = []
        for f in scalar_fields:
            gv = safe_get(g, f)
            ov = safe_get(o, f)
            g_present = bool(gv) if not isinstance(gv, int) else gv is not None
            o_present = bool(ov) if not isinstance(ov, int) else ov is not None
            if g_present:
                totals["gemini_filled"][f] += 1
            if o_present:
                totals["openai_filled"][f] += 1
            if g_present and o_present:
                totals["field_both_present"][f] += 1
                if field_match(gv, ov):
                    totals["field_match"][f] += 1
                else:
                    diffs.append(f"{f}: G={gv} / O={ov}")
            elif not g_present and not o_present:
                totals["field_match"][f] += 1
                totals["field_both_present"][f] += 1

        # List comparison
        list_info = []
        for f in list_fields:
            gc = count_list(g, f)
            oc = count_list(o, f)
            totals["list_gemini"][f] += gc
            totals["list_openai"][f] += oc
            list_info.append(f"{f[:3]}={gc}/{oc}")

        icon = "✓" if not diffs else "△"
        diff_str = f"  [{'; '.join(diffs)}]" if diffs else ""
        print(
            f"  [{i + 1:2d}] {c.name:8s} {icon}  G={g_time:.1f}s O={o_time:.1f}s  "
            f"{' '.join(list_info)}{diff_str}"
        )

    # --- Summary ---
    n = totals["ok_count"]
    if not n:
        print("\nNo successful pairs to compare.")
        return

    gt = totals["gemini_time"]
    ot = totals["openai_time"]

    # Cost (actual pricing)
    # Gemini 3.1 Flash Lite: $0.25/1M input, $1.50/1M output
    # GPT-5.4 Nano: $0.20/1M input, $1.25/1M output
    est_tokens_in = 1500
    est_tokens_out = 800
    g_cost = n * (est_tokens_in * 0.25 + est_tokens_out * 1.50) / 1_000_000
    o_cost = n * (est_tokens_in * 0.20 + est_tokens_out * 1.25) / 1_000_000

    print(f"\n{'=' * 80}")
    print(f"  RESULTS  (both succeeded: {n}/{len(resumes)})")
    print(f"{'=' * 80}")

    print(f"\n  [Time]")
    print(f"    {'':12s} {'Gemini':>10s} {'GPT-5.4N':>10s}")
    print(f"    {'Total':12s} {gt:>9.1f}s {ot:>9.1f}s")
    print(f"    {'Avg/resume':12s} {gt / n:>9.1f}s {ot / n:>9.1f}s")
    print(
        f"    {'Failures':12s} {totals['gemini_fail']:>10d} {totals['openai_fail']:>10d}"
    )

    print(f"\n  [Cost estimate ({n} resumes)]")
    print(f"    {'':12s} {'Gemini':>10s} {'GPT-5.4N':>10s}")
    print(
        f"    {'Total':12s} {'$' + f'{g_cost:.4f}':>10s} {'$' + f'{o_cost:.4f}':>10s}"
    )

    print(
        f"\n  [Scalar fields — match when both present (normalized: lowercase, no spaces)]"
    )
    print(f"    {'field':12s} {'match':>8s} {'G filled':>8s} {'O filled':>8s}")
    for f in scalar_fields:
        bp = totals["field_both_present"][f]
        m = totals["field_match"][f]
        gf = totals["gemini_filled"][f]
        of = totals["openai_filled"][f]
        pct = f"{m / bp * 100:.0f}%" if bp else "-"
        print(f"    {f:12s} {m:>3d}/{bp:<3d} {pct:>4s} {gf:>8d} {of:>8d}")

    total_match = sum(totals["field_match"][f] for f in scalar_fields)
    total_bp = sum(totals["field_both_present"][f] for f in scalar_fields)
    pct = f"{total_match / total_bp * 100:.1f}%" if total_bp else "-"
    print(f"    {'TOTAL':12s} {total_match:>3d}/{total_bp:<3d} {pct:>4s}")

    print(f"\n  [List fields — total items extracted]")
    print(f"    {'field':14s} {'Gemini':>8s} {'GPT-5.4N':>8s} {'diff':>8s}")
    for f in list_fields:
        gc = totals["list_gemini"][f]
        oc = totals["list_openai"][f]
        diff = oc - gc
        sign = "+" if diff > 0 else ""
        print(f"    {f:14s} {gc:>8d} {oc:>8d} {sign + str(diff):>8s}")

    print(f"\n{'=' * 80}\n")


if __name__ == "__main__":
    run()
