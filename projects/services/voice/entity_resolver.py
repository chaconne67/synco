"""Voice entity resolver — converts human-readable names to UUIDs.

Handles disambiguation when multiple candidates share the same name,
and resolves submissions for various workflow stages.
"""

from __future__ import annotations

import dataclasses
import uuid as uuid_mod
from typing import Any

from accounts.models import Organization
from candidates.models import Candidate
from projects.models import Contact, Project, Submission


@dataclasses.dataclass
class CandidateResolution:
    status: str  # "resolved" | "ambiguous" | "not_found"
    candidate_id: uuid_mod.UUID | None
    candidates: list[dict[str, Any]]  # [{id, name, email, phone}]


def resolve_candidate(
    *,
    name: str,
    organization: Organization,
    project: Project | None = None,
) -> CandidateResolution:
    """Resolve a candidate name to a UUID within the organization scope."""
    matches = Candidate.objects.filter(
        name__icontains=name.strip(),
        owned_by=organization,
    ).order_by("name", "-created_at")[:20]

    candidate_list = [
        {"id": c.pk, "name": c.name, "email": c.email, "phone": c.phone}
        for c in matches
    ]

    if len(candidate_list) == 0:
        return CandidateResolution(status="not_found", candidate_id=None, candidates=[])
    if len(candidate_list) == 1:
        return CandidateResolution(
            status="resolved",
            candidate_id=candidate_list[0]["id"],
            candidates=candidate_list,
        )

    # Multiple matches: try to narrow by project context
    if project:
        project_candidate_ids = set(
            Contact.objects.filter(project=project).values_list(
                "candidate_id", flat=True
            )
        )
        in_project = [c for c in candidate_list if c["id"] in project_candidate_ids]
        if len(in_project) == 1:
            return CandidateResolution(
                status="resolved",
                candidate_id=in_project[0]["id"],
                candidates=candidate_list,
            )

    return CandidateResolution(
        status="ambiguous",
        candidate_id=None,
        candidates=candidate_list,
    )


def resolve_candidate_list(
    *,
    names: list[str],
    organization: Organization,
    project: Project | None = None,
) -> dict[str, Any]:
    """Resolve multiple candidate names to UUIDs."""
    resolved_ids: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    not_found: list[str] = []

    for name in names:
        result = resolve_candidate(
            name=name, organization=organization, project=project
        )
        if result.status == "resolved":
            resolved_ids.append(str(result.candidate_id))
        elif result.status == "ambiguous":
            ambiguous.append({"name": name, "candidates": result.candidates})
        else:
            not_found.append(name)

    return {
        "resolved_ids": resolved_ids,
        "ambiguous": ambiguous,
        "not_found": not_found,
    }


def resolve_submission(
    *,
    candidate_id: uuid_mod.UUID,
    project: Project,
) -> dict[str, Any]:
    """Resolve the best eligible submission for a candidate in a project."""
    eligible = Submission.objects.filter(
        project=project,
        candidate_id=candidate_id,
        status=Submission.Status.PASSED,
    ).order_by("-created_at")

    subs = [
        {"id": s.pk, "status": s.status, "created_at": str(s.created_at)}
        for s in eligible
    ]

    if len(subs) == 0:
        return {"status": "not_found", "submission_id": None, "submissions": []}
    if len(subs) == 1:
        return {
            "status": "resolved",
            "submission_id": subs[0]["id"],
            "submissions": subs,
        }
    return {"status": "ambiguous", "submission_id": None, "submissions": subs}


def resolve_submission_for_interview(
    *,
    candidate_id: uuid_mod.UUID,
    project: Project,
) -> dict[str, Any]:
    """Resolve eligible submission for interview scheduling. PASSED status required."""
    eligible = Submission.objects.filter(
        project=project,
        candidate_id=candidate_id,
        status=Submission.Status.PASSED,
    ).order_by("-created_at")

    subs = list(eligible)
    if len(subs) == 0:
        return {"status": "not_found", "submission_id": None}
    if len(subs) == 1:
        return {"status": "resolved", "submission_id": subs[0].pk}
    return {
        "status": "ambiguous",
        "submission_id": None,
        "submissions": [{"id": str(s.pk)} for s in subs],
    }


def resolve_submission_for_offer(
    *,
    candidate_id: uuid_mod.UUID,
    project: Project,
) -> dict[str, Any]:
    """Resolve eligible submission for offer creation.

    A submission is offer-eligible if it has PASSED status and no existing offer.
    """
    eligible = Submission.objects.filter(
        project=project,
        candidate_id=candidate_id,
        status=Submission.Status.PASSED,
    ).order_by("-created_at")

    valid = []
    for sub in eligible:
        has_offer = False
        try:
            _ = sub.offer
            has_offer = True
        except Exception:
            has_offer = False
        if not has_offer:
            valid.append(sub)

    if len(valid) == 0:
        return {"status": "not_found", "submission_id": None}
    if len(valid) == 1:
        return {"status": "resolved", "submission_id": valid[0].pk}
    return {
        "status": "ambiguous",
        "submission_id": None,
        "submissions": [{"id": str(s.pk)} for s in valid],
    }
