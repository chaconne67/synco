"""긴급도 자동 산정 로직.

Phase 1: Contact/Offer models deleted, old ProjectStatus replaced.
Phase 2-6: Will be rewritten with ActionItem-based urgency (due_at, overdue).
"""

from __future__ import annotations

from projects.models import Project


def collect_all_actions(project: Project) -> list[dict]:
    """Phase 1 stub — urgency system will be rebuilt with ActionItem."""
    return []


def compute_project_urgency(project: Project) -> dict | None:
    """Phase 1 stub — urgency system will be rebuilt with ActionItem."""
    return None
