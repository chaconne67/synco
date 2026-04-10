"""Org-scoped candidate identity matching for resume uploads."""
from accounts.models import Organization
from candidates.models import Candidate
from candidates.services.candidate_identity import (
    CandidateComparisonContext,
    _latest_parsed_resume,
    normalize_phone_for_matching,
)


def identify_candidate_for_org(
    extracted: dict,
    organization: Organization,
) -> CandidateComparisonContext | None:
    """Find existing candidate within organization scope only."""
    # 1. Email match (org-scoped)
    email = (extracted.get("email") or "").strip().lower()
    if email:
        candidate = (
            Candidate.objects.filter(
                email__iexact=email,
                owned_by=organization,
            )
            .order_by("-created_at")
            .first()
        )
        if candidate:
            compared_resume = _latest_parsed_resume(candidate)
            previous_data = _build_previous_data(candidate, compared_resume)
            return CandidateComparisonContext(
                candidate=candidate,
                compared_resume=compared_resume,
                match_reason="email",
                previous_data=previous_data,
            )

    # 2. Phone match (org-scoped)
    phone = extracted.get("phone") or ""
    normalized = normalize_phone_for_matching(phone)
    if len(normalized) >= 10:
        candidate = (
            Candidate.objects.filter(
                phone_normalized=normalized,
                owned_by=organization,
            )
            .order_by("-created_at")
            .first()
        )
        if candidate:
            compared_resume = _latest_parsed_resume(candidate)
            previous_data = _build_previous_data(candidate, compared_resume)
            return CandidateComparisonContext(
                candidate=candidate,
                compared_resume=compared_resume,
                match_reason="phone",
                previous_data=previous_data,
            )

    return None


def _build_previous_data(candidate, compared_resume) -> dict:
    """Build previous_data dict for cross-version comparison."""
    if not compared_resume or not compared_resume.raw_text:
        return {}
    return candidate.raw_extracted_json or {}
