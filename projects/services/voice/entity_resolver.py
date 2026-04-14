"""Voice entity resolver — converts human-readable names to UUIDs.

Handles disambiguation when multiple candidates share the same name,
and resolves submissions for various workflow stages.

Phase 1: Contact references removed. Submission.Status removed.
Phase 2-6: Will be rewritten with Application/ActionItem-based flow.
"""

from __future__ import annotations

import dataclasses
import uuid as uuid_mod
from typing import Any

from accounts.models import Organization
from candidates.models import Candidate
from projects.models import Project, Submission


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
    matches = Candidate.objects.filter(
        name__icontains=name,
        owned_by=organization,
    )

    candidate_list = [
        {
            "id": str(c.pk),
            "name": c.name,
            "email": c.email or "",
            "phone": c.phone or "",
        }
        for c in matches
    ]

    if not candidate_list:
        return CandidateResolution(status="not_found", candidate_id=None, candidates=[])
    if len(candidate_list) == 1:
        return CandidateResolution(
            status="resolved",
            candidate_id=matches[0].pk,
            candidates=candidate_list,
        )

    # Multiple matches: try to narrow by project context
    # Phase 1: Contact model deleted. Use Application instead.
    if project:
        from projects.models import Application

        project_candidate_ids = {
            str(cid)
            for cid in Application.objects.filter(project=project).values_list(
                "candidate_id", flat=True
            )
        }
        in_project = [c for c in candidate_list if c["id"] in project_candidate_ids]
        if len(in_project) == 1:
            return CandidateResolution(
                status="resolved",
                candidate_id=uuid_mod.UUID(in_project[0]["id"]),
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
    """Resolve the best eligible submission for a candidate in a project.

    Phase 1: Submission.Status removed. This is a legacy stub.
    """
    return {"status": "not_found", "submission_id": None, "submissions": []}


def resolve_submission_for_interview(
    *,
    candidate_id: uuid_mod.UUID,
    project: Project,
) -> dict[str, Any]:
    """Legacy stub — Submission model no longer has status/project/candidate FK."""
    return {"status": "not_found", "submission_id": None}


def resolve_submission_for_offer(
    *,
    candidate_id: uuid_mod.UUID,
    project: Project,
) -> dict[str, Any]:
    """Legacy stub — Offer model deleted."""
    return {"status": "not_found", "submission_id": None}
