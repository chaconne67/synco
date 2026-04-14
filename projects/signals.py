"""Signal handlers for phase recomputation and status/result sync.

Phase 2a: ActionItem/Application changes trigger phase recompute.
Project.closed_at drives status/result sync.
HIRED processing is owned by hire() service, not signals.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from projects.models import (
    ActionItem,
    Application,
    Project,
    ProjectStatus,
)
from projects.services.phase import compute_project_phase

logger = logging.getLogger(__name__)


def _sync_phase(project: Project) -> None:
    new_phase = compute_project_phase(project)
    # Read current phase from DB — the in-memory object may be stale
    current_phase = Project.objects.filter(pk=project.pk).values_list(
        "phase", flat=True
    ).first()
    if current_phase != new_phase:
        Project.objects.filter(pk=project.pk).update(phase=new_phase)


@receiver([post_save, post_delete], sender=ActionItem)
def recompute_phase_on_action_change(sender, instance, **kwargs):
    try:
        project = instance.application.project
    except Application.DoesNotExist:
        return
    _sync_phase(project)


@receiver([post_save, post_delete], sender=Application)
def recompute_phase_on_application_change(sender, instance, **kwargs):
    _sync_phase(instance.project)


@receiver(post_save, sender=Project)
def sync_project_status_field(sender, instance: Project, **kwargs):
    """Keep closed_at and status/result in sync. Uses .update() to avoid recursion."""
    expected_status = ProjectStatus.CLOSED if instance.closed_at else ProjectStatus.OPEN

    # [I-03] reopen clears result — prevents DB CheckConstraint violation
    updates = {}
    if instance.status != expected_status:
        updates["status"] = expected_status
    if expected_status == ProjectStatus.OPEN and instance.result:
        updates["result"] = ""
    if updates:
        Project.objects.filter(pk=instance.pk).update(**updates)
