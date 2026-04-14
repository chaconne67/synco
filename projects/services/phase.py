from projects.models import (
    ActionItem,
    ActionItemStatus,
    Project,
    ProjectPhase,
)

SUBMIT_TO_CLIENT_CODE = "submit_to_client"


def compute_project_phase(project: Project) -> str:
    """OR rule: submit_to_client completed on any active Application -> screening."""
    if project.closed_at is not None:
        return project.phase  # closed projects keep last value

    has_submitted_active = ActionItem.objects.filter(
        application__project=project,
        application__dropped_at__isnull=True,
        application__hired_at__isnull=True,
        action_type__code=SUBMIT_TO_CLIENT_CODE,
        status=ActionItemStatus.DONE,
    ).exists()

    return ProjectPhase.SCREENING if has_submitted_active else ProjectPhase.SEARCHING
