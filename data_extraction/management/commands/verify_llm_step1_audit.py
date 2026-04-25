"""Step B4 audit — 원본 텍스트 vs LLM Step 1 결과 자동 대조.

휴리스틱 메트릭:
  company_coverage   원본에서 detect한 회사 후보 중 결과 careers에 매치된 비율
  school_coverage    원본의 학교/university 키워드 라인 중 결과 educations에 매치된 비율
  year_coverage      원본의 4자리 연도 중 결과 dates에 반영된 비율
  email_match        원본 이메일이 결과에 반영
  phone_match        원본 전화번호가 결과에 반영

Usage:
    uv run python manage.py verify_llm_step1_audit \\
        --input-dir snapshots/step_b4_llm_step1 \\
        --output snapshots/step_b4_llm_step1_audit.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand


_COMPANY_PAT = re.compile(
    r"(?:[가-힣A-Za-z0-9&\.\-]{2,40}"
    r"(?:전자|화학|중공업|건설|상사|컴퍼니|코리아|은행|증권|카드|보험|"
    r"제약|병원|연구소|회사|호텔|에너지|시스템|텔레콤|솔루션|테크|레저|"
    r"미디어|모터스|디스플레이|전기|반도체|네트웍스?|네트워크|뱅크|커뮤니케이션))|"
    r"(?:㈜|\(주\)|주식회사)\s*[가-힣A-Za-z0-9&\.\- ]{2,40}|"
    r"[가-힣A-Za-z0-9&\.\- ]{2,40}\s*(?:㈜|\(주\)|주식회사)|"
    r"\b[A-Z][A-Za-z&\-]{1,30}(?:\s+[A-Z][A-Za-z&\-]{1,30}){0,4}"
    r"\s+(?:Co\.?|Corp\.?|Inc\.?|Ltd\.?|LLC|Group|Company)\b"
)
_SCHOOL_PAT = re.compile(
    r"[가-힣A-Za-z]{2,30}(?:대학교|대학원|대학|학교)|"
    r"[A-Za-z][A-Za-z\s]{2,40}\s+University|"
    r"\bUniversity\s+of\s+[A-Z][A-Za-z\s]{2,40}",
    re.IGNORECASE,
)
_YEAR_PAT = re.compile(r"(?:19|20)\d{2}")
_EMAIL_PAT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PAT = re.compile(r"01\d[-.\s]?\d{3,4}[-.\s]?\d{4}")


def _norm(s: str) -> str:
    return re.sub(r"[\s\-_,\.()㈜（）]", "", s.lower())


def _company_set_from_text(text: str) -> set[str]:
    raw = set()
    for m in _COMPANY_PAT.finditer(text):
        s = m.group(0).strip()
        if 2 < len(s) < 60:
            raw.add(_norm(s))
    return raw


def _school_set_from_text(text: str) -> set[str]:
    raw = set()
    for m in _SCHOOL_PAT.finditer(text):
        s = m.group(0).strip()
        if 2 < len(s) < 60:
            raw.add(_norm(s))
    return raw


def _years_from_text(text: str) -> set[int]:
    return {int(y) for y in _YEAR_PAT.findall(text) if 1950 <= int(y) <= 2030}


def _result_companies(extracted: dict) -> set[str]:
    out = set()
    for c in extracted.get("careers") or []:
        for k in ("company", "company_en"):
            v = c.get(k)
            if v:
                out.add(_norm(v))
    return out


def _result_schools(extracted: dict) -> set[str]:
    out = set()
    for e in extracted.get("educations") or []:
        v = e.get("institution")
        if v:
            out.add(_norm(v))
    return out


def _result_years(extracted: dict) -> set[int]:
    out = set()
    for c in extracted.get("careers") or []:
        for k in ("start_date", "end_date", "duration_text", "date_evidence"):
            v = c.get(k) or ""
            for y in _YEAR_PAT.findall(str(v)):
                yi = int(y)
                if 1950 <= yi <= 2030:
                    out.add(yi)
    for e in extracted.get("educations") or []:
        for k in ("start_year", "end_year"):
            v = e.get(k)
            if v and 1950 <= int(v) <= 2030:
                out.add(int(v))
    by = extracted.get("birth_year")
    if by:
        out.add(int(by))
    return out


def _coverage(set_text: set, set_result: set) -> tuple[float, set, set]:
    """fuzzy coverage: result 항목이 text 항목의 substring이거나 그 반대인 매치 카운트.

    For numeric sets (years), falls back to equality.
    """
    if not set_text:
        return 1.0, set(), set()
    matched_text = set()
    is_string = next(iter(set_text)) is not None and isinstance(next(iter(set_text)), str)
    for t in set_text:
        for r in set_result:
            if not is_string:
                if t == r:
                    matched_text.add(t)
                    break
            elif t and r and (t in r or r in t):
                matched_text.add(t)
                break
    missing_in_result = set_text - matched_text
    if is_string:
        extra_in_result = {
            r for r in set_result
            if not any((t in r or r in t) for t in set_text if isinstance(t, str))
        }
    else:
        extra_in_result = set_result - set_text
    return len(matched_text) / len(set_text), missing_in_result, extra_in_result


class Command(BaseCommand):
    help = "Step B4 audit: cross-check extracted JSON against original text."

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
            target = data.get("target") or {
                "category": data.get("category"),
                "file_id": data.get("file_id"),
                "file_name": data.get("file_name"),
                "text_path": data.get("text_path"),
            }
            text_path = target.get("text_path")
            extracted = data.get("result")
            if not text_path or not extracted:
                continue
            text = Path(text_path).read_text(encoding="utf-8")

            cset_text = _company_set_from_text(text)
            cset_result = _result_companies(extracted)
            sset_text = _school_set_from_text(text)
            sset_result = _result_schools(extracted)
            yset_text = _years_from_text(text)
            yset_result = _result_years(extracted)

            c_cov, c_missing, c_extra = _coverage(cset_text, cset_result)
            s_cov, s_missing, s_extra = _coverage(sset_text, sset_result)
            y_cov, y_missing, y_extra = _coverage(yset_text, yset_result)

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
                "len": len(text),
                "careers_n": len(extracted.get("careers") or []),
                "edus_n": len(extracted.get("educations") or []),
                "company_cov": c_cov,
                "company_missing": sorted(c_missing),
                "school_cov": s_cov,
                "school_missing": sorted(s_missing),
                "year_cov": y_cov,
                "year_missing": sorted(y_missing),
                "email_match": email_match,
                "phone_match": phone_match,
                "name": extracted.get("name"),
                "birth_year": extracted.get("birth_year"),
            })

        # ---- render markdown ----
        lines = []
        lines.append("# LLM Step 1 — 원본 vs 추출 자동 대조 결과")
        lines.append("")
        lines.append(f"검사 대상: {len(rows)}건")
        lines.append("")
        lines.append("## 메트릭 정의")
        lines.append("- **company_cov**: 원본에서 detect한 회사 후보 중 결과 careers에 (substring) 매치된 비율")
        lines.append("- **school_cov**: 원본 학교/university 패턴 중 결과 educations에 매치된 비율")
        lines.append("- **year_cov**: 원본의 4자리 연도 중 결과(careers/edus/birth)에 반영된 비율")
        lines.append("- **email_match / phone_match**: 원본 이메일·전화번호와 결과 일치 (n/a = 원본에 없음)")
        lines.append("")
        lines.append("## 요약 표")
        lines.append("")
        lines.append("| Cat | File | name | birth | careers | edus | company% | school% | year% | email | phone |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['category']} | {r['file_name'][:25]} | {r['name'] or '–'} | "
                f"{r['birth_year'] or '–'} | {r['careers_n']} | {r['edus_n']} | "
                f"{r['company_cov']*100:.0f} | {r['school_cov']*100:.0f} | {r['year_cov']*100:.0f} | "
                f"{r['email_match']} | {r['phone_match']} |"
            )

        # outliers
        lines.append("")
        lines.append("## 의심 outlier (회사/학교/연도 coverage < 70%)")
        lines.append("")
        outliers = [r for r in rows if min(r["company_cov"], r["school_cov"], r["year_cov"]) < 0.7]
        for r in outliers:
            lines.append(f"### {r['category']} / {r['file_name']}")
            lines.append("")
            lines.append(f"- name: {r['name']!r}, birth: {r['birth_year']}")
            lines.append(f"- careers: {r['careers_n']}건, educations: {r['edus_n']}건")
            lines.append(f"- company coverage: **{r['company_cov']*100:.0f}%**")
            if r["company_missing"]:
                lines.append(f"  - 원본에서 detect됐는데 결과에 없는 회사 후보 (휴리스틱):")
                for m in r["company_missing"][:8]:
                    lines.append(f"    - `{m}`")
            lines.append(f"- school coverage: **{r['school_cov']*100:.0f}%**")
            if r["school_missing"]:
                lines.append(f"  - 결과에 없는 학교 후보:")
                for m in r["school_missing"][:8]:
                    lines.append(f"    - `{m}`")
            lines.append(f"- year coverage: **{r['year_cov']*100:.0f}%**")
            if r["year_missing"]:
                lines.append(f"  - 결과에 반영 안 된 원본 연도: {sorted(r['year_missing'])[:15]}")
            lines.append("")

        # email/phone misses
        miss_email = [r for r in rows if r["email_match"] == "miss"]
        miss_phone = [r for r in rows if r["phone_match"] == "miss"]
        if miss_email or miss_phone:
            lines.append("## 이메일/전화 매치 실패")
            lines.append("")
            for r in miss_email:
                lines.append(f"- email miss: {r['file_name']}")
            for r in miss_phone:
                lines.append(f"- phone miss: {r['file_name']}")

        # macro stats
        if rows:
            avg_c = sum(r["company_cov"] for r in rows) / len(rows)
            avg_s = sum(r["school_cov"] for r in rows) / len(rows)
            avg_y = sum(r["year_cov"] for r in rows) / len(rows)
            lines.append("")
            lines.append("## 평균 메트릭")
            lines.append(f"- company coverage 평균: **{avg_c*100:.1f}%**")
            lines.append(f"- school coverage 평균: **{avg_s*100:.1f}%**")
            lines.append(f"- year coverage 평균: **{avg_y*100:.1f}%**")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Audit saved: {out_path}"))
        self.stdout.write(f"평균 company {avg_c*100:.1f}% / school {avg_s*100:.1f}% / year {avg_y*100:.1f}%")
        if outliers:
            self.stdout.write(f"⚠ outlier: {len(outliers)}건")
