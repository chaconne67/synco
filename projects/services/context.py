"""ProjectContext CRUD + FORM_REGISTRY + resume/restore."""

from __future__ import annotations

import json
from typing import Any

from django.urls import reverse

from projects.models import ProjectContext


# --- Validation ---

REQUIRED_KEYS = {"form"}
MAX_DRAFT_SIZE = 50_000  # 50KB


def validate_draft_data(data: Any) -> bool:
    """Validate draft_data structure and size."""
    if not isinstance(data, dict):
        return False
    if not REQUIRED_KEYS.issubset(data.keys()):
        return False
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_DRAFT_SIZE:
        return False
    return True


# --- CRUD ---


def save_context(
    *,
    project,
    user,
    last_step: str,
    pending_action: str,
    draft_data: dict,
) -> ProjectContext:
    """Create or update context for this project+consultant pair."""
    ctx, _created = ProjectContext.objects.update_or_create(
        project=project,
        consultant=user,
        defaults={
            "last_step": last_step,
            "pending_action": pending_action,
            "draft_data": draft_data,
        },
    )
    return ctx


def get_active_context(project, user) -> ProjectContext | None:
    """Return the active context for this project+consultant, or None."""
    return ProjectContext.objects.filter(
        project=project,
        consultant=user,
    ).first()


def discard_context(project, user) -> bool:
    """Delete context for this project+consultant. Returns True if deleted."""
    count, _ = ProjectContext.objects.filter(
        project=project,
        consultant=user,
    ).delete()
    return count > 0


# --- Form Registry ---

FORM_REGISTRY: dict[str, dict[str, Any]] = {
    "contact_create": {
        "url_name": "projects:contact_create",
        "url_kwargs": lambda ctx: {"pk": str(ctx.project_id)},
    },
    "contact_update": {
        "url_name": "projects:contact_update",
        "url_kwargs": lambda ctx: {
            "pk": str(ctx.project_id),
            "contact_pk": ctx.draft_data.get("fields", {}).get("contact_id", ""),
        },
    },
    "submission_create": {
        "url_name": "projects:submission_create",
        "url_kwargs": lambda ctx: {"pk": str(ctx.project_id)},
    },
}


def get_resume_url(ctx: ProjectContext) -> str | None:
    """Build the resume redirect URL for this context, or None if unknown form."""
    form_name = ctx.draft_data.get("form", ctx.last_step)
    entry = FORM_REGISTRY.get(form_name)
    if not entry:
        return None
    base_url = reverse(entry["url_name"], kwargs=entry["url_kwargs"](ctx))
    return f"{base_url}?resume={ctx.pk}"
