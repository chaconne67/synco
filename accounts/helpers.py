from django.shortcuts import get_object_or_404

from accounts.models import Organization


def _get_org(request):
    """Return the current user's Organization via active Membership, or 404."""
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status="active",
    )
