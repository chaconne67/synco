"""Context processors for projects app."""

from projects.models import ProjectApproval


def pending_approval_count(request):
    """Inject pending approval count for OWNER users."""
    if not request.user.is_authenticated:
        return {}

    try:
        membership = request.user.membership
    except Exception:
        return {}

    if membership.role != "owner":
        return {}

    count = ProjectApproval.objects.filter(
        project__organization=membership.organization,
        status=ProjectApproval.Status.PENDING,
    ).count()

    return {"pending_approval_count": count}
