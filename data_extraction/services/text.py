"""Extract text from .doc and .docx resume files."""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date

from docx import Document


def extract_text(file_path: str) -> str:
    """Extract text from a resume file based on its extension.

    Supports .docx (python-docx), .doc (antiword / LibreOffice fallback),
    and .pdf (PyMuPDF).
    Raises ValueError for unsupported file formats.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".docx":
        return _extract_docx(file_path)
    elif ext == ".doc":
        return _extract_doc(file_path)
    elif ext == ".pdf":
        return _extract_pdf(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")


def _extract_docx(file_path: str) -> str:
    """Extract text from a .docx file.

    Tries python-docx first (paragraphs, tables, textboxes).
    If the result is too short, tries LibreOffice and picks the longer result.
    This handles cases where python-docx silently misses table data.
    """
    docx_text = ""
    try:
        doc = Document(file_path)
        parts: list[str] = []

        # 1) Body paragraphs
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text)

        # 2) Tables
        for table in doc.tables:
            for row in table.rows:
                row_text = "\t".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    parts.append(row_text)

        # 3) Textboxes (VML w:txbxContent) — often contain headers with
        #    company names, positions, and date ranges in Korean resumes
        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        seen: set[str] = set()
        for txbx in doc.element.body.findall(f".//{{{ns_w}}}txbxContent"):
            t_elems = txbx.findall(f".//{{{ns_w}}}t")
            text = " ".join((t.text or "") for t in t_elems).strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(text)

        docx_text = "\n".join(parts)
    except Exception:
        pass

    # Try LibreOffice and pick the result with richer content.
    # Length alone is not a reliable indicator — a longer result may still
    # miss table data while a shorter result captures it.
    try:
        lo_text = _extract_doc_libreoffice(file_path)
    except Exception:
        lo_text = ""

    if not _strip_bom(lo_text):
        return docx_text or ""
    if not _strip_bom(docx_text):
        return lo_text

    # Pick the result with more structural resume signals
    docx_score = _content_richness_score(docx_text)
    lo_score = _content_richness_score(lo_text)
    return lo_text if lo_score > docx_score else docx_text


def _extract_doc(file_path: str) -> str:
    """Extract text from a .doc file. Tries both LibreOffice and antiword,
    picks the result with richer content."""
    lo_text = ""
    aw_text = ""

    try:
        lo_text = _extract_doc_libreoffice(file_path)
    except Exception:
        pass

    try:
        aw_text = _extract_doc_antiword(file_path)
    except Exception:
        pass

    if not _strip_bom(lo_text) and not _strip_bom(aw_text):
        return ""
    if not _strip_bom(lo_text):
        return aw_text
    if not _strip_bom(aw_text):
        return lo_text

    lo_score = _content_richness_score(lo_text)
    aw_score = _content_richness_score(aw_text)
    return lo_text if lo_score >= aw_score else aw_text


def _extract_pdf(file_path: str) -> str:
    """Extract text from a PDF file using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Run: uv add pymupdf")

    doc = fitz.open(file_path)
    parts: list[str] = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            parts.append(text)
    doc.close()
    return "\n".join(parts)


def _extract_doc_antiword(file_path: str) -> str:
    """Extract text from a .doc file using antiword."""
    result = subprocess.run(
        ["antiword", file_path],
        capture_output=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"antiword failed with return code {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )

    # Try decoding with multiple encodings
    for encoding in ("utf-8", "euc-kr", "cp949", "latin-1"):
        try:
            return result.stdout.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue

    # latin-1 should never fail, but just in case
    return result.stdout.decode("latin-1")


def _extract_doc_libreoffice(file_path: str) -> str:
    """Extract text from a .doc file using LibreOffice headless conversion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                tmpdir,
                file_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice failed: {result.stderr.decode('utf-8', errors='replace')}"
            )

        # Find the converted .txt file
        basename = os.path.splitext(os.path.basename(file_path))[0]
        txt_path = os.path.join(tmpdir, f"{basename}.txt")

        if not os.path.exists(txt_path):
            raise RuntimeError(f"LibreOffice conversion failed: {txt_path} not found")

        # Try decoding with multiple encodings
        with open(txt_path, "rb") as f:
            raw = f.read()
        for encoding in ("utf-8", "euc-kr", "cp949", "latin-1"):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue

        # latin-1 should never fail, but just in case
        return raw.decode("latin-1")


def preprocess_resume_text(text: str) -> str:
    """Clean and deduplicate resume text to reduce LLM token usage.

    First applies sanitize_input_text for encoding/control char cleanup,
    then removes blank lines, compresses whitespace, deduplicates identical
    and similar lines (70%+ word overlap), and strips noise patterns.
    Typically reduces text by 25-40%.
    """
    from data_extraction.services.extraction.sanitizers import sanitize_input_text

    text = sanitize_input_text(text)
    lines = text.split("\n")

    # 1) Remove blank lines, compress whitespace
    lines = [re.sub(r"\s{2,}", " ", line).strip() for line in lines if line.strip()]

    # 2) Remove exact duplicate lines (preserve order)
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        normalized = line.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(line)

    # 3) Remove near-duplicate lines (70%+ word overlap with recent lines)
    final: list[str] = []
    for line in unique:
        words = set(line.lower().split())
        if len(words) < 3:
            final.append(line)
            continue
        is_dup = False
        for existing in final[-10:]:
            existing_words = set(existing.lower().split())
            if existing_words:
                overlap = len(words & existing_words) / max(
                    len(words), len(existing_words)
                )
                if overlap > 0.7:
                    is_dup = True
                    break
        if not is_dup:
            final.append(line)

    # 4) Remove noise patterns (basic PC skills, etc.)
    # Only remove short lines that are purely noise — skip lines with dates
    # or company-name suffixes to avoid deleting career history.
    noise = [
        "워드/엑셀",
        "ms-office",
        "ms office",
        "powerpoint",
        "computer :",
        "computer:",
    ]
    date_pattern = re.compile(r"\d{4}")
    company_suffixes = ("㈜", "주식회사", "(주)", "co.", "corp", "inc")
    cleaned: list[str] = []
    for line in final:
        lower = line.lower()
        if any(n in lower for n in noise):
            # Preserve lines that look like career entries
            if date_pattern.search(line) or any(s in lower for s in company_suffixes):
                cleaned.append(line)
                continue
            # Only drop short noise lines (< 40 chars)
            if len(line.strip()) < 40:
                continue
        cleaned.append(line)
    final = cleaned

    return "\n".join(final)


def _content_richness_score(text: str) -> int:
    """Score text by how many resume-structural signals it contains.

    Checks for presence of career/education keywords, contact info patterns,
    and date patterns — not just length.
    """
    score = 0
    t = text.lower()

    # Career signals
    for kw in ["경력", "재직", "회사명", "근무기간", "experience", "career"]:
        if kw in t:
            score += 1

    # Education signals
    for kw in ["학력", "대학", "졸업", "university", "education"]:
        if kw in t:
            score += 1

    # Contact signals
    if re.search(r"010[-.\s]?\d{4}[-.\s]?\d{4}", text):
        score += 2
    if re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        score += 2

    # Date patterns (YYYY.MM or YYYY-MM)
    date_count = len(re.findall(r"\d{4}[.-/]\d{1,2}", text))
    score += min(date_count, 5)  # cap at 5

    # Company name patterns (㈜, (주))
    company_count = len(re.findall(r"㈜|\(주\)|주식회사", text))
    score += min(company_count, 3)

    return score


def _strip_bom(text: str) -> str:
    """Strip BOM and whitespace."""
    return text.replace("\ufeff", "").strip()


def _has_substantive_text(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[0-9A-Za-z\uac00-\ud7a3]", text))


def classify_text_quality(text: str) -> str:
    """Classify extracted text quality before LLM extraction.

    Returns: 'ok', 'too_short', 'garbled', 'empty'
    """
    if not text or not text.strip():
        return "empty"

    stripped = text.strip()

    # Check ratio of meaningful characters (Korean, Latin, digits)
    alnum_chars = sum(1 for c in stripped if c.isalnum() or "\uac00" <= c <= "\ud7a3")
    if len(stripped) > 0 and alnum_chars / len(stripped) < 0.3:
        return "garbled"

    # Reject truly empty content only — actual quality is judged post-extraction
    if len(stripped) < 50:
        return "too_short"

    return "ok"


@dataclass(frozen=True)
class BirthYearFilterResult:
    passed: bool
    active: bool
    cutoff_year: int | None = None
    detected_year: int | None = None
    source: str = ""
    evidence: str = ""
    reason: str = ""


def normalize_birth_year_filter_value(value: int, *, today: date | None = None) -> int:
    """Normalize a 2-digit age or 4-digit birth year into a cutoff birth year."""
    today = today or date.today()
    if 10 <= value <= 99:
        return today.year - value
    if 1900 <= value <= today.year:
        return value
    raise ValueError("birth-year filter must be a 2-digit age or 4-digit birth year")


def extract_birth_year_from_text(text: str, *, today: date | None = None) -> dict | None:
    """Extract a likely birth year from resume text using contextual patterns."""
    today = today or date.today()
    if not text:
        return None

    patterns = [
        (
            "text_dob",
            re.compile(
                r"(?:생년월일|출생(?:년도|연도)?|출생일|birthday|birth|dob|date\s+of\s+birth)"
                r"[\s:：\-]*"
                r"(?P<year>(?:19|20)\d{2})[.\-/년\s]*(?:\d{1,2})?",
                re.IGNORECASE,
            ),
        ),
        (
            "text_birth_year",
            re.compile(r"(?P<year>(?:19|20)\d{2})\s*년\s*생"),
        ),
        (
            "text_short_birth_year",
            re.compile(r"(?P<yy>\d{2})\s*년\s*생"),
        ),
    ]
    for source, pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        year = _normalize_birth_match(match, today=today)
        if year:
            return {
                "birth_year": year,
                "source": source,
                "evidence": match.group(0).strip()[:120],
            }

    rrn = re.search(r"(?<!\d)(?P<yy>\d{2})(?P<mm>0[1-9]|1[0-2])(?P<dd>[0-3]\d)[-\s]?(?P<gender>[1-4])", text)
    if rrn:
        yy = int(rrn.group("yy"))
        gender = rrn.group("gender")
        year = (1900 + yy) if gender in {"1", "2"} else (2000 + yy)
        if 1900 <= year <= today.year:
            return {
                "birth_year": year,
                "source": "resident_registration_number",
                "evidence": rrn.group(0).strip()[:120],
            }

    age_match = re.search(
        r"(?:나이|연령|age)[\s:：\-]*(?:만\s*)?(?P<age>\d{2})\s*(?:세|years?\s+old)?",
        text,
        re.IGNORECASE,
    )
    if age_match:
        age = int(age_match.group("age"))
        if 10 <= age <= 99:
            return {
                "birth_year": today.year - age,
                "source": "age",
                "evidence": age_match.group(0).strip()[:120],
            }

    return None


def passes_birth_year_filter(
    text: str,
    filter_value: int | None,
    *,
    enabled: bool = False,
    today: date | None = None,
) -> BirthYearFilterResult:
    """Return whether text passes the pre-LLM birth-year cutoff filter.

    The filter passes resumes whose detected birth year is greater than or equal
    to the cutoff. A 2-digit value is interpreted as age and converted to a
    birth-year cutoff using the current year.
    """
    if not enabled or filter_value is None:
        return BirthYearFilterResult(passed=True, active=False)

    cutoff = normalize_birth_year_filter_value(filter_value, today=today)
    extracted = extract_birth_year_from_text(text, today=today)
    if not extracted:
        return BirthYearFilterResult(
            passed=False,
            active=True,
            cutoff_year=cutoff,
            reason="birth year not found in extracted text",
        )

    detected = extracted["birth_year"]
    passed = detected >= cutoff
    return BirthYearFilterResult(
        passed=passed,
        active=True,
        cutoff_year=cutoff,
        detected_year=detected,
        source=extracted["source"],
        evidence=extracted["evidence"],
        reason=(
            ""
            if passed
            else f"detected birth year {detected} is before cutoff {cutoff}"
        ),
    )


def _normalize_birth_match(match: re.Match, *, today: date) -> int | None:
    if match.groupdict().get("year"):
        year = int(match.group("year"))
    else:
        yy = int(match.group("yy"))
        year = 1900 + yy if yy >= 50 else 2000 + yy
    if 1900 <= year <= today.year:
        return year
    return None


def extract_text_libreoffice(file_path: str) -> str:
    """Public wrapper for LibreOffice-based text extraction.

    Used by retry pipeline when python-docx extraction misses content.
    """
    return _extract_doc_libreoffice(file_path)
