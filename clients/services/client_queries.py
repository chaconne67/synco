from django.db.models import Count, Q

from clients.models import Client


def list_clients_with_stats(org, **filters):
    """Clients queryset annotated with offers/success/placed/active counts.

    Returns a queryset. Apply filters via keyword args (see Task 7).
    """
    qs = (
        Client.objects.filter(organization=org)
        .annotate(
            offers_count=Count("projects", distinct=True),
            success_count=Count(
                "projects",
                filter=Q(projects__result="success"),
                distinct=True,
            ),
            active_count=Count(
                "projects",
                filter=Q(projects__status="open"),
                distinct=True,
            ),
            placed_count=Count(
                "projects__applications",
                filter=Q(projects__applications__hired_at__isnull=False),
                distinct=True,
            ),
        )
        .order_by("-created_at")
    )
    return qs
