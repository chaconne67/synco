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


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters for comparison."""
    return re.sub(r"\D", "", phone)


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


def _latest_parsed_resume(candidate: Candidate) -> Resume | None:
    """Return the most recent parsed resume for cross-version comparison."""
    return (
        candidate.resumes.filter(
            processing_status=Resume.ProcessingStatus.PARSED,
        )
        .order_by("-version")
        .first()
    )
