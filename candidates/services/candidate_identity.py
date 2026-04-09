"""Identify whether an incoming resume belongs to an existing candidate.

Policy: auto-merge ONLY on email or phone match.
Name-only matches are NOT used for auto-merge to prevent false merges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from candidates.models import Candidate, Resume


@dataclass
class IdentityMatch:
    """Result of candidate identity matching."""

    candidate: Candidate
    compared_resume: Resume | None
    match_reason: str  # "email" or "phone"


@dataclass
class CandidateComparisonContext:
    """Shared comparison context for matching and cross-version checks."""

    candidate: Candidate
    compared_resume: Resume | None
    match_reason: str
    previous_data: dict


_PHONE_SPLIT_RE = re.compile(r"\s*(?:/|,|;|\||\n)+\s*")
_PHONE_TOKEN_RE = re.compile(r"\+?\d[\d()\-\s]{7,}\d")


def select_primary_phone(phone: str) -> str:
    """Pick a single representative phone number from noisy LLM output."""
    raw = (phone or "").strip()
    if not raw:
        return ""

    candidates = [part.strip() for part in _PHONE_SPLIT_RE.split(raw) if part.strip()]
    if not candidates:
        candidates = [raw]

    matches = [match.group(0).strip() for match in _PHONE_TOKEN_RE.finditer(raw)]
    for match in matches:
        if match not in candidates:
            candidates.append(match)

    if not candidates:
        return raw

    def priority(value: str) -> tuple[int, int]:
        digits = re.sub(r"\D", "", value)
        is_korean = digits.startswith(
            ("010", "011", "016", "017", "018", "019", "8210")
        )
        fits_model = len(value) <= 30
        return (
            0 if is_korean else 1,
            0 if fits_model else 1,
        )

    return sorted(candidates, key=priority)[0]


def _normalize_phone(phone: str) -> str:
    """Normalize Korean phone numbers for comparison."""
    phone = select_primary_phone(phone)
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0082"):
        digits = digits[2:]
    if digits.startswith("82"):
        local_digits = digits[2:]
        if local_digits and not local_digits.startswith("0"):
            return f"0{local_digits}"
        return local_digits
    return digits


def normalize_phone_for_matching(phone: str | None) -> str:
    """Normalize a phone value into a stable comparison key."""
    return _normalize_phone(phone or "")


def identify_candidate(extracted: dict) -> IdentityMatch | None:
    """Find an existing candidate matching the extracted resume data.

    Matching order (first match wins):
      1. email exact match (case-insensitive)
      2. phone normalized match

    Returns None if no confident match is found.
    """
    # 1. Email match
    email = (extracted.get("email") or "").strip().lower()
    if email:
        candidate = (
            Candidate.objects.filter(email__iexact=email)
            .order_by("-created_at")
            .first()
        )
        if candidate:
            return IdentityMatch(
                candidate=candidate,
                compared_resume=_latest_parsed_resume(candidate),
                match_reason="email",
            )

    # 2. Phone match (normalized)
    phone = extracted.get("phone") or ""
    normalized = normalize_phone_for_matching(phone)
    if len(normalized) >= 10:
        candidate = (
            Candidate.objects.filter(phone_normalized=normalized)
            .order_by("-created_at")
            .first()
        )
        if candidate:
            return IdentityMatch(
                candidate=candidate,
                compared_resume=_latest_parsed_resume(candidate),
                match_reason="phone",
            )

    return None


def build_candidate_comparison_context(
    extracted: dict,
) -> CandidateComparisonContext | None:
    """Build a single source of truth for comparison and persistence."""
    identity = identify_candidate(extracted)
    if not identity:
        return None

    return CandidateComparisonContext(
        candidate=identity.candidate,
        compared_resume=identity.compared_resume,
        match_reason=identity.match_reason,
        previous_data=_build_candidate_snapshot(identity.candidate),
    )


def _latest_parsed_resume(candidate: Candidate) -> Resume | None:
    """Return the most recent parsed resume for cross-version comparison."""
    if (
        candidate.current_resume
        and candidate.current_resume.processing_status
        == Resume.ProcessingStatus.STRUCTURED
    ):
        return candidate.current_resume

    return (
        candidate.resumes.filter(
            processing_status=Resume.ProcessingStatus.STRUCTURED,
        )
        .order_by("-version")
        .first()
    )


def _build_candidate_snapshot(candidate: Candidate) -> dict:
    """Serialize the candidate's current profile for cross-version checks."""
    return {
        "birth_year": candidate.birth_year,
        "careers": [
            {
                "company": c.company,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "position": c.position,
            }
            for c in candidate.careers.all()
        ],
        "educations": [
            {
                "institution": e.institution,
                "degree": e.degree,
                "major": e.major,
                "start_year": e.start_year,
                "end_year": e.end_year,
            }
            for e in candidate.educations.all()
        ],
    }
