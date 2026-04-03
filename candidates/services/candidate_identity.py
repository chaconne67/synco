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


def _normalize_phone(phone: str) -> str:
    """Normalize Korean phone numbers for comparison."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0082"):
        digits = digits[2:]
    if digits.startswith("82"):
        local_digits = digits[2:]
        if local_digits and not local_digits.startswith("0"):
            return f"0{local_digits}"
        return local_digits
    return digits


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
    normalized = _normalize_phone(phone)
    if len(normalized) >= 10:
        for c in Candidate.objects.exclude(phone="").order_by("-created_at"):
            if _normalize_phone(c.phone) == normalized:
                return IdentityMatch(
                    candidate=c,
                    compared_resume=_latest_parsed_resume(c),
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
        and candidate.current_resume.processing_status == Resume.ProcessingStatus.PARSED
    ):
        return candidate.current_resume

    return (
        candidate.resumes.filter(
            processing_status=Resume.ProcessingStatus.PARSED,
        )
        .order_by("-version")
        .first()
    )


def _build_candidate_snapshot(candidate: Candidate) -> dict:
    """Serialize the candidate's current profile for cross-version checks."""
    return {
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
