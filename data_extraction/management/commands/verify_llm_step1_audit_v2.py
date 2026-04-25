"""Step B4 audit v2 — 양방향 + 본인 경력 패턴 한정 휴리스틱.

v1의 한계: 본문에서 거론된 타사·기관·부서명을 회사 후보로 잡아 false positive 다수.
v2 개선:
  - 회사 후보를 "시작일 ~ 종료일 + 회사 키워드" 한 줄 패턴으로 한정 (본인 경력 가능성 높음)
  - 양방향 측정:
    * recall   원본의 본인-경력 패턴 중 결과에 매치된 비율 (누락 측정)
    * precision 결과 careers/educations 중 원본에 substring 매치되는 비율 (환각 측정)

Usage:
    uv run python manage.py verify_llm_step1_audit_v2 \\
        --input-dir snapshots/step_b4_llm_step1 \\
        --output snapshots/step_b4_llm_step1_audit_v2.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand


# 본인 경력으로 강하게 의심되는 라인 패턴: 시작연도(~종료연도) + 한 라인 안에 회사 토큰
_OWN_CAREER_LINE = re.compile(
    r"(?:19|20)\d{2}\s*[.\-/년]\s*\d{1,2}"
    r"[^\n]{0,80}"
    r"(?:"
    r"㈜|\(주\)|주식회사|"
    r"(?:Co\.?|Corp\.?|Inc\.?|Ltd\.?|LLC|Group|Company)\b|"
    r"[가-힣A-Za-z]{2,30}(?:전자|화학|중공업|건설|상사|컴퍼니|코리아|은행|증권|카드|보험|"
    r"제약|병원|연구소|호텔|에너지|시스템|텔레콤|솔루션|테크|레저|미디어|모터스|"
    r"디스플레이|전기|반도체|네트웍스?|네트워크|뱅크|커뮤니케이션|연구센터|연구원)"
    r")",
    re.IGNORECASE,
)

# 학교 라인: 대학교/대학원/university (대학교 키워드만 — 고등학교 제외)
_OWN_SCHOOL_LINE = re.compile(
    r"[가-힣A-Za-z]{2,30}(?:대학교|대학원|전문대학|university|college)",
    re.IGNORECASE,
)

_EMAIL_PAT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PAT = re.compile(r"01\d[-.\s]?\d{3,4}[-.\s]?\d{4}")


def _norm(s: str) -> str:
    return re.sub(r"[\s\-_,\.()㈜（）]", "", s.lower())


def _extract_own_careers_from_text(text: str) -> list[str]:
    """원본에서 본인 경력으로 의심되는 한 줄 단위 후보."""
    out = []
    for line in text.split("\n"):
        if _OWN_CAREER_LINE.search(line):
            out.append(line.strip())
    return out


def _extract_own_schools_from_text(text: str) -> set[str]:
    out = set()
    for m in _OWN_SCHOOL_LINE.finditer(text):
        out.add(_norm(m.group(0)))
    return out


def _result_companies_norm(extracted: dict) -> set[str]:
    out = set()
    for c in extracted.get("careers") or []:
        for k in ("company", "company_en"):
            v = c.get(k)
            if v:
                out.add(_norm(v))
    return out


def _result_schools_norm(extracted: dict) -> set[str]:
    out = set()
    for e in extracted.get("educations") or []:
        v = e.get("institution")
        if v:
            out.add(_norm(v))
    return out


def _line_has_company_in_results(line: str, result_companies: set[str]) -> bool:
    """원본 라인이 결과 회사 중 하나를 포함하는지."""
    n = _norm(line)
    return any(c in n for c in result_companies if len(c) >= 2)


def _company_in_text(company_norm: str, text_norm: str) -> bool:
    if not company_norm or len(company_norm) < 2:
        return False
    return company_norm in text_norm


class Command(BaseCommand):
    help = "Step B4 audit v2: bidirectional, own-career-pattern only."

    def add_arguments(self, parser):
        parser.add_argument("--input-dir", type=str, required=True)
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        in_dir = Path(options["input_dir"])
        out_path = Path(options["output"])

        files = sorted(in_dir.glob("*.json"))
        rows = []

        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            target = data.get("target") or data
            text_path = target.get("text_path")
            extracted = data.get("result")
            if not text_path or not extracted:
                continue
            text = Path(text_path).read_text(encoding="utf-8")
            text_norm = _norm(text)

            # --- recall (누락 측정): 본인 경력 라인 중 결과에 매치된 비율 ---
            own_lines = _extract_own_careers_from_text(text)
            result_companies = _result_companies_norm(extracted)
            recall_matched = sum(
                1 for ln in own_lines
                if _line_has_company_in_results(ln, result_companies)
            )
            recall = (recall_matched / len(own_lines)) if own_lines else 1.0
            missing_lines = [
                ln for ln in own_lines
                if not _line_has_company_in_results(ln, result_companies)
            ][:8]

            # --- precision (환각 측정): 결과 회사가 원본에 존재하는 비율 ---
            precision_matched = sum(
                1 for c in result_companies if _company_in_text(c, text_norm)
            )
            precision = (precision_matched / len(result_companies)) if result_companies else 1.0
            hallucinated = [
                c for c in result_companies if not _company_in_text(c, text_norm)
            ][:8]

            # --- school recall ---
            own_schools = _extract_own_schools_from_text(text)
            result_schools = _result_schools_norm(extracted)
            school_recall_matched = sum(
                1 for s in own_schools
                if any(s in r or r in s for r in result_schools)
            )
            school_recall = (
                (school_recall_matched / len(own_schools)) if own_schools else 1.0
            )
            missing_schools = sorted({
                s for s in own_schools
                if not any(s in r or r in s for r in result_schools)
            })[:5]

            # --- email/phone ---
            text_emails = set(_EMAIL_PAT.findall(text))
            text_phones = set(_PHONE_PAT.findall(text))
            res_email = (extracted.get("email") or "").strip()
            res_phone = (extracted.get("phone") or "").strip()

            email_match = (
                "n/a" if not text_emails else
                ("ok" if any(e == res_email for e in text_emails) else "miss")
            )
            phone_match = (
                "n/a" if not text_phones else
                ("ok" if any(_norm(p) in _norm(res_phone) or _norm(res_phone) in _norm(p)
                             for p in text_phones if res_phone) else "miss")
            )

            rows.append({
                "category": target.get("category"),
                "file_name": target.get("file_name"),
                "name": extracted.get("name"),
                "birth_year": extracted.get("birth_year"),
                "careers_n": len(extracted.get("careers") or []),
                "edus_n": len(extracted.get("educations") or []),
                "own_career_lines": len(own_lines),
                "recall_matched": recall_matched,
                "recall": recall,
                "missing_lines": missing_lines,
                "precision_matched": precision_matched,
                "precision_total": len(result_companies),
                "precision": precision,
                "hallucinated": hallucinated,
                "school_recall": school_recall,
                "missing_schools": missing_schools,
                "email_match": email_match,
                "phone_match": phone_match,
            })

        # ---- render markdown ----
        lines = []
        lines.append("# LLM Step 1 — 원본 vs 추출 (audit v2)")
        lines.append("")
        lines.append("v2 개선: 양방향 + 본인 경력 패턴 한정")
        lines.append("- **recall**: 원본의 본인 경력으로 의심되는 라인('YYYY...회사키워드') 중 결과에 매치된 비율 (누락 측정)")
        lines.append("- **precision**: 결과 careers의 회사명이 원본에 substring으로 존재하는 비율 (환각 측정)")
        lines.append("- **school_recall**: 원본의 대학교/대학원 패턴 중 결과 educations에 매치된 비율 (고등학교는 제외)")
        lines.append("")
        lines.append("## 전체 표")
        lines.append("")
        lines.append("| Cat | File | careers | edus | own_lines | recall | precision | school_recall | email | phone |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            r_pct = f"{r['recall']*100:.0f}%" + (f" ({r['recall_matched']}/{r['own_career_lines']})" if r['own_career_lines'] else " (n/a)")
            p_pct = f"{r['precision']*100:.0f}%" + (f" ({r['precision_matched']}/{r['precision_total']})" if r['precision_total'] else " (n/a)")
            sr_pct = f"{r['school_recall']*100:.0f}%"
            lines.append(
                f"| {r['category']} | {r['file_name'][:25]} | {r['careers_n']} | {r['edus_n']} | "
                f"{r['own_career_lines']} | {r_pct} | {p_pct} | {sr_pct} | "
                f"{r['email_match']} | {r['phone_match']} |"
            )

        # outliers
        outliers_recall = [r for r in rows if r["recall"] < 0.7 and r["own_career_lines"] > 0]
        outliers_precision = [r for r in rows if r["precision"] < 0.7 and r["precision_total"] > 0]

        if outliers_recall or outliers_precision:
            lines.append("")
            lines.append("## 의심 outlier (recall <70% 또는 precision <70%)")
            lines.append("")
            shown = set()
            for r in outliers_recall + outliers_precision:
                if r["file_name"] in shown:
                    continue
                shown.add(r["file_name"])
                lines.append(f"### {r['category']} / {r['file_name']}")
                lines.append("")
                lines.append(f"- recall: **{r['recall']*100:.0f}%** ({r['recall_matched']}/{r['own_career_lines']})")
                if r["missing_lines"]:
                    lines.append(f"  - 결과에 누락 의심 (원본 본인 경력 라인):")
                    for ln in r["missing_lines"][:5]:
                        lines.append(f"    - `{ln[:90]}`")
                lines.append(f"- precision: **{r['precision']*100:.0f}%** ({r['precision_matched']}/{r['precision_total']})")
                if r["hallucinated"]:
                    lines.append(f"  - 환각 의심 (결과에 있으나 원본에 없는 회사):")
                    for c in r["hallucinated"][:5]:
                        lines.append(f"    - `{c}`")
                if r["missing_schools"]:
                    lines.append(f"- school 누락 의심:")
                    for s in r["missing_schools"]:
                        lines.append(f"    - `{s}`")
                lines.append("")

        # macro stats
        if rows:
            recall_with_data = [r for r in rows if r["own_career_lines"] > 0]
            prec_with_data = [r for r in rows if r["precision_total"] > 0]
            avg_recall = sum(r["recall"] for r in recall_with_data) / len(recall_with_data) if recall_with_data else 0
            avg_prec = sum(r["precision"] for r in prec_with_data) / len(prec_with_data) if prec_with_data else 0
            avg_sch = sum(r["school_recall"] for r in rows) / len(rows)
            lines.append("")
            lines.append("## 평균 메트릭")
            lines.append(f"- 평균 recall (본인 경력 누락 측정): **{avg_recall*100:.1f}%**")
            lines.append(f"- 평균 precision (환각 측정): **{avg_prec*100:.1f}%**")
            lines.append(f"- 평균 school recall: **{avg_sch*100:.1f}%**")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Audit v2 saved: {out_path}"))
        if rows:
            self.stdout.write(
                f"평균 recall {avg_recall*100:.1f}% / precision {avg_prec*100:.1f}% / school {avg_sch*100:.1f}%"
            )
            if outliers_recall:
                self.stdout.write(f"⚠ recall outlier: {len(outliers_recall)}건")
            if outliers_precision:
                self.stdout.write(f"⚠ precision outlier: {len(outliers_precision)}건")
