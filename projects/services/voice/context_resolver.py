"""Screen context -> parsing hints with server-side permission check."""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Any

from accounts.models import Organization, User
from projects.models import Project

logger = logging.getLogger(__name__)

# Pages that imply project scope
PROJECT_PAGES = {
    "project_detail",
    "project_tab_search",
    "project_tab_contacts",
    "project_tab_submissions",
    "project_tab_interviews",
    "project_tab_offers",
}


def resolve_context(
    *,
    user: User,
    organization: Organization,
    context_hint: dict[str, Any],
) -> dict[str, Any]:
    """Resolve client context hint to verified server context.

    The client sends page name and optional project_id via data-voice-context.
    This function verifies the project belongs to the user's organization and
    enriches the context with server-side data.

    Returns dict with keys: page, project_id, project_title, scope, tab.
    """
    page = context_hint.get("page", "unknown")
    raw_project_id = context_hint.get("project_id")
    tab = context_hint.get("tab", "")

    project_id = None
    project_title = ""
    scope = "global"

    # Validate project_id if provided
    if raw_project_id:
        try:
            pid = uuid_mod.UUID(str(raw_project_id))
            proj = Project.objects.filter(
                pk=pid,
                organization=organization,
            ).first()
            if proj:
                project_id = proj.pk
                project_title = proj.title
                scope = "project"
        except (ValueError, AttributeError):
            logger.warning("Invalid project_id in voice context: %s", raw_project_id)

    # Override scope based on page
    if page in PROJECT_PAGES and project_id:
        scope = "project"
    elif page in PROJECT_PAGES and not project_id:
        # Page implies project but no valid project — fall back to global
        scope = "global"

    return {
        "page": page,
        "project_id": project_id,
        "project_title": project_title,
        "scope": scope,
        "tab": tab,
    }
