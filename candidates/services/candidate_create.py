from __future__ import annotations

from django.db import transaction

from candidates.models import Candidate


def find_duplicate(email: str | None, phone: str | None) -> Candidate | None:
    """Return existing candidate matching email or phone (exact), else None."""
    if email:
        hit = Candidate.objects.filter(email__iexact=email.strip()).first()
        if hit:
            return hit
    if phone:
        normalized = "".join(c for c in phone if c.isdigit())
        if normalized:
            hit = Candidate.objects.filter(phone__contains=normalized[-8:]).first()
            if hit:
                return hit
    return None


@transaction.atomic
def create_candidate(data: dict, user=None) -> Candidate:
    """Create a Candidate. Caller is responsible for duplicate check."""
    field_whitelist = {
        "name", "email", "phone", "current_company", "current_position",
        "birth_year", "source", "address",
    }
    kwargs = {k: v for k, v in data.items() if k in field_whitelist and v not in (None, "")}
    if "birth_year" in kwargs:
        try:
            kwargs["birth_year"] = int(kwargs["birth_year"])
        except (ValueError, TypeError):
            kwargs.pop("birth_year")
    primary_category = data.get("primary_category")
    if primary_category:
        kwargs["primary_category"] = primary_category
    candidate = Candidate.objects.create(**kwargs)
    return candidate
