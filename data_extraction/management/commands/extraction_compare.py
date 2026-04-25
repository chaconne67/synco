"""두 extraction snapshot(realtime/batch)을 비교해 시간·비용·품질 리포트 생성.

Usage:
    uv run python manage.py extraction_compare \\
        --realtime snapshots/realtime.json \\
        --batch snapshots/batch.json \\
        --realtime-tokens snapshots/realtime_tokens.json \\
        --batch-tokens snapshots/batch_tokens.json \\
        --output snapshots/comparison.md
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Generate comparison report (time/cost/quality) between realtime and batch snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--realtime", type=str, required=True)
        parser.add_argument("--batch", type=str, required=True)
        parser.add_argument(
            "--realtime-tokens",
            type=str,
            default="",
            help="extract --token-usage-output 으로 저장된 JSON",
        )
        parser.add_argument("--batch-tokens", type=str, default="")
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        rt = self._load(options["realtime"])
        bt = self._load(options["batch"])
        rt_tokens = self._load_optional(options.get("realtime_tokens"))
        bt_tokens = self._load_optional(options.get("batch_tokens"))

        rt_records = {r["drive_file_id"]: r for r in rt.get("records", [])}
        bt_records = {r["drive_file_id"]: r for r in bt.get("records", [])}
        common_ids = sorted(set(rt_records) & set(bt_records))

        report = self._render(
            rt=rt,
            bt=bt,
            rt_tokens=rt_tokens,
            bt_tokens=bt_tokens,
            rt_records=rt_records,
            bt_records=bt_records,
            common_ids=common_ids,
        )

        out = Path(options["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Report saved: {out}"))

    def _load(self, path: str) -> dict:
        if not path:
            raise CommandError("path required")
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _load_optional(self, path: str | None) -> dict | None:
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Quality metrics
    # ------------------------------------------------------------------

    def _quality_metrics(self, records: Iterable[dict]) -> dict:
        records = list(records)
        n = len(records)
        if n == 0:
            return {"count": 0}
        with_candidate = [r for r in records if r.get("candidate_id")]
        nc = len(with_candidate)
        auto_confirmed = sum(
            1 for r in with_candidate if r.get("validation_status") == "auto_confirmed"
        )
        needs_review = sum(
            1 for r in with_candidate if r.get("validation_status") == "needs_review"
        )
        failed_status = sum(
            1 for r in with_candidate if r.get("validation_status") == "failed"
        )
        no_candidate = n - nc

        confidence_scores = [
            r.get("confidence_score") or 0.0 for r in with_candidate
        ]
        avg_conf = sum(confidence_scores) / nc if nc else 0.0

        red_total = 0
        yellow_total = 0
        for r in with_candidate:
            for f in r.get("integrity_flags") or []:
                sev = f.get("severity")
                if sev == "RED":
                    red_total += 1
                elif sev == "YELLOW":
                    yellow_total += 1

        # Field 채움률
        def filled(field: str) -> int:
            return sum(1 for r in with_candidate if r.get(field))

        def filled_truthy(field: str) -> int:
            return sum(
                1
                for r in with_candidate
                if r.get(field) not in (None, "", [], {})
            )

        career_count_avg = (
            sum(r.get("career_count") or 0 for r in with_candidate) / nc if nc else 0
        )
        education_count_avg = (
            sum(r.get("education_count") or 0 for r in with_candidate) / nc if nc else 0
        )
        skills_count_avg = (
            sum(r.get("skills_count") or 0 for r in with_candidate) / nc if nc else 0
        )

        education_with_status = 0
        education_total = 0
        for r in with_candidate:
            for edu in r.get("educations") or []:
                education_total += 1
                if edu.get("status"):
                    education_with_status += 1

        return {
            "count": n,
            "with_candidate": nc,
            "no_candidate": no_candidate,
            "auto_confirmed": auto_confirmed,
            "needs_review": needs_review,
            "failed_status": failed_status,
            "auto_confirmed_pct": _pct(auto_confirmed, nc),
            "needs_review_pct": _pct(needs_review, nc),
            "no_candidate_pct": _pct(no_candidate, n),
            "avg_confidence": round(avg_conf, 3),
            "red_flags_total": red_total,
            "yellow_flags_total": yellow_total,
            "red_flags_avg": round(red_total / nc, 2) if nc else 0,
            "yellow_flags_avg": round(yellow_total / nc, 2) if nc else 0,
            "name_filled_pct": _pct(filled("name"), nc),
            "birth_year_filled_pct": _pct(filled("birth_year"), nc),
            "phone_filled_pct": _pct(filled("phone"), nc),
            "email_filled_pct": _pct(filled("email"), nc),
            "summary_filled_pct": _pct(filled_truthy("summary"), nc),
            "current_company_filled_pct": _pct(filled_truthy("current_company"), nc),
            "total_experience_filled_pct": _pct(
                sum(
                    1
                    for r in with_candidate
                    if r.get("total_experience_years") is not None
                ),
                nc,
            ),
            "career_count_avg": round(career_count_avg, 2),
            "education_count_avg": round(education_count_avg, 2),
            "skills_count_avg": round(skills_count_avg, 2),
            "education_status_filled_pct": _pct(
                education_with_status, education_total
            ),
        }

    # ------------------------------------------------------------------
    # Pair comparison
    # ------------------------------------------------------------------

    def _pair_diff(
        self, rt_records: dict, bt_records: dict, common_ids: list[str]
    ) -> dict:
        career_count_diffs = []
        education_count_diffs = []
        confidence_diffs = []
        agreement = {
            "same_validation_status": 0,
            "name_match": 0,
            "name_present_both": 0,
            "career_count_equal": 0,
            "education_count_equal": 0,
            "company_set_overlap_avg": [],
            "institution_set_overlap_avg": [],
        }
        for did in common_ids:
            rt = rt_records[did]
            bt = bt_records[did]
            if rt.get("candidate_id") and bt.get("candidate_id"):
                if rt.get("validation_status") == bt.get("validation_status"):
                    agreement["same_validation_status"] += 1
                if rt.get("name") and bt.get("name"):
                    agreement["name_present_both"] += 1
                    if rt["name"] == bt["name"]:
                        agreement["name_match"] += 1

                rt_cc = rt.get("career_count") or 0
                bt_cc = bt.get("career_count") or 0
                career_count_diffs.append(abs(rt_cc - bt_cc))
                if rt_cc == bt_cc:
                    agreement["career_count_equal"] += 1

                rt_ec = rt.get("education_count") or 0
                bt_ec = bt.get("education_count") or 0
                education_count_diffs.append(abs(rt_ec - bt_ec))
                if rt_ec == bt_ec:
                    agreement["education_count_equal"] += 1

                rt_companies = {
                    (c.get("company") or "").strip().lower()
                    for c in rt.get("careers") or []
                    if c.get("company")
                }
                bt_companies = {
                    (c.get("company") or "").strip().lower()
                    for c in bt.get("careers") or []
                    if c.get("company")
                }
                if rt_companies or bt_companies:
                    union = rt_companies | bt_companies
                    inter = rt_companies & bt_companies
                    agreement["company_set_overlap_avg"].append(
                        len(inter) / len(union)
                    )

                rt_inst = {
                    (e.get("institution") or "").strip().lower()
                    for e in rt.get("educations") or []
                    if e.get("institution")
                }
                bt_inst = {
                    (e.get("institution") or "").strip().lower()
                    for e in bt.get("educations") or []
                    if e.get("institution")
                }
                if rt_inst or bt_inst:
                    union = rt_inst | bt_inst
                    inter = rt_inst & bt_inst
                    agreement["institution_set_overlap_avg"].append(
                        len(inter) / len(union)
                    )

                rt_conf = rt.get("confidence_score") or 0
                bt_conf = bt.get("confidence_score") or 0
                confidence_diffs.append(abs(rt_conf - bt_conf))

        n_pair = len(common_ids)
        return {
            "common_pairs": n_pair,
            "validation_status_agreement_pct": _pct(
                agreement["same_validation_status"], n_pair
            ),
            "name_match_pct": _pct(
                agreement["name_match"], agreement["name_present_both"]
            ),
            "career_count_equal_pct": _pct(agreement["career_count_equal"], n_pair),
            "education_count_equal_pct": _pct(
                agreement["education_count_equal"], n_pair
            ),
            "career_count_diff_avg": round(
                _avg(career_count_diffs), 2
            ),
            "education_count_diff_avg": round(
                _avg(education_count_diffs), 2
            ),
            "company_jaccard_avg": round(
                _avg(agreement["company_set_overlap_avg"]), 3
            ),
            "institution_jaccard_avg": round(
                _avg(agreement["institution_set_overlap_avg"]), 3
            ),
            "confidence_diff_avg": round(_avg(confidence_diffs), 3),
        }

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _render(
        self,
        *,
        rt,
        bt,
        rt_tokens,
        bt_tokens,
        rt_records,
        bt_records,
        common_ids,
    ) -> str:
        rt_q = self._quality_metrics(rt.get("records", []))
        bt_q = self._quality_metrics(bt.get("records", []))
        pair = self._pair_diff(rt_records, bt_records, common_ids)

        lines = []
        lines.append("# Extraction Test Report — Realtime vs Batch")
        lines.append("")
        lines.append(f"- Realtime captured: {rt.get('captured_at')}")
        lines.append(f"- Batch captured:    {bt.get('captured_at')}")
        lines.append(
            f"- Records: realtime={rt_q['count']}, batch={bt_q['count']}, "
            f"common={len(common_ids)}"
        )
        lines.append("")
        lines.append("## 시간·비용")
        lines.append("")
        lines.append("| 항목 | 리얼타임 | 배치 |")
        lines.append("|---|---|---|")
        if rt_tokens and bt_tokens:
            lines.append(
                f"| Wall clock | {rt_tokens.get('elapsed_seconds')}s "
                f"| {bt_tokens.get('elapsed_seconds')}s |"
            )
            lines.append(
                f"| LLM 호출 수 | {rt_tokens.get('llm_calls')} "
                f"| {bt_tokens.get('llm_calls')} |"
            )
            lines.append(
                f"| Input tokens | {rt_tokens.get('input_tokens'):,} "
                f"| {bt_tokens.get('input_tokens'):,} |"
            )
            lines.append(
                f"| Output tokens | {rt_tokens.get('output_tokens'):,} "
                f"| {bt_tokens.get('output_tokens'):,} |"
            )
            lines.append(
                f"| 비용(USD est.) | ${rt_tokens.get('cost_usd_estimate')} "
                f"| ${bt_tokens.get('cost_usd_estimate')} |"
            )
            lines.append(
                f"| 비용(KRW est.) | ₩{rt_tokens.get('cost_krw_estimate'):,.0f} "
                f"| ₩{bt_tokens.get('cost_krw_estimate'):,.0f} |"
            )
            n_rt = max(rt_q["count"], 1)
            n_bt = max(bt_q["count"], 1)
            lines.append(
                f"| 건당 평균 시간 | {rt_tokens.get('elapsed_seconds') / n_rt:.1f}s "
                f"| {bt_tokens.get('elapsed_seconds') / n_bt:.1f}s |"
            )
        else:
            lines.append("| (token usage JSON 누락) | – | – |")
        lines.append("")
        if rt_tokens or bt_tokens:
            note = (rt_tokens or bt_tokens or {}).get("pricing_note", "")
            lines.append(f"_{note}_")
            lines.append("")

        lines.append("## 품질 (단일 모드 메트릭)")
        lines.append("")
        lines.append("| 지표 | 리얼타임 | 배치 |")
        lines.append("|---|---|---|")
        for label, key in [
            ("후보자 생성 성공", "with_candidate"),
            ("실패 (no_candidate)", "no_candidate"),
            ("auto_confirmed", "auto_confirmed"),
            ("needs_review", "needs_review"),
            ("failed status", "failed_status"),
            ("auto_confirmed %", "auto_confirmed_pct"),
            ("needs_review %", "needs_review_pct"),
            ("평균 confidence_score", "avg_confidence"),
            ("RED 플래그 총합", "red_flags_total"),
            ("YELLOW 플래그 총합", "yellow_flags_total"),
            ("RED 평균/건", "red_flags_avg"),
            ("YELLOW 평균/건", "yellow_flags_avg"),
            ("name 채움 %", "name_filled_pct"),
            ("birth_year 채움 %", "birth_year_filled_pct"),
            ("phone 채움 %", "phone_filled_pct"),
            ("email 채움 %", "email_filled_pct"),
            ("summary 채움 %", "summary_filled_pct"),
            ("current_company 채움 %", "current_company_filled_pct"),
            ("총 경력 채움 %", "total_experience_filled_pct"),
            ("평균 careers 수", "career_count_avg"),
            ("평균 educations 수", "education_count_avg"),
            ("평균 skills 수", "skills_count_avg"),
            ("Education.status 채움 %", "education_status_filled_pct"),
        ]:
            lines.append(f"| {label} | {rt_q.get(key, '-')} | {bt_q.get(key, '-')} |")
        lines.append("")

        lines.append("## 양 모드 페어 비교 (동일 drive_file_id)")
        lines.append("")
        lines.append("| 지표 | 값 |")
        lines.append("|---|---|")
        lines.append(f"| 비교 가능 페어 수 | {pair['common_pairs']} |")
        lines.append(
            f"| validation_status 일치율 | {pair['validation_status_agreement_pct']}% |"
        )
        lines.append(f"| 이름 일치율 (둘 다 추출 시) | {pair['name_match_pct']}% |")
        lines.append(
            f"| careers 수 일치율 | {pair['career_count_equal_pct']}% |"
        )
        lines.append(
            f"| educations 수 일치율 | {pair['education_count_equal_pct']}% |"
        )
        lines.append(f"| careers 수 차이 평균 | {pair['career_count_diff_avg']} |")
        lines.append(
            f"| educations 수 차이 평균 | {pair['education_count_diff_avg']} |"
        )
        lines.append(
            f"| 회사 집합 Jaccard 평균 | {pair['company_jaccard_avg']} |"
        )
        lines.append(
            f"| 학교 집합 Jaccard 평균 | {pair['institution_jaccard_avg']} |"
        )
        lines.append(f"| confidence_score 차이 평균 | {pair['confidence_diff_avg']} |")
        lines.append("")
        lines.append(
            "_Jaccard = 두 집합의 교집합 크기 / 합집합 크기 (1.0 = 완전 일치, 0.0 = 완전 다름)_"
        )
        lines.append("")
        return "\n".join(lines)


def _pct(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round(100.0 * numerator / denominator, 1)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
