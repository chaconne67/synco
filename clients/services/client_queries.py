from django.db.models import Count, Q

from clients.models import Client, IndustryCategory


def _category_values(names):
    """Convert enum names (e.g. 'BIO_PHARMA') to DB values (e.g. '바이오/제약')."""
    values = []
    for name in names or []:
        try:
            values.append(IndustryCategory[name].value)
        except KeyError:
            continue
    return values


def list_clients_with_stats(
    org,
    *,
    categories=None,
    sizes=None,
    regions=None,
    offers_range=None,
    success_status=None,
):
    qs = (
        Client.objects.filter(organization=org)
        .annotate(
            offers_count=Count("projects", distinct=True),
            success_count=Count(
                "projects", filter=Q(projects__result="success"), distinct=True
            ),
            active_count=Count(
                "projects", filter=Q(projects__status="open"), distinct=True
            ),
            placed_count=Count(
                "projects__applications",
                filter=Q(projects__applications__hired_at__isnull=False),
                distinct=True,
            ),
        )
        .order_by("-created_at")
    )

    if categories:
        cat_values = _category_values(categories)
        if cat_values:
            qs = qs.filter(industry__in=cat_values)

    if sizes:
        qs = qs.filter(size__in=sizes)

    if regions:
        qs = qs.filter(region__in=regions)

    if offers_range:
        qs = _apply_offers_range(qs, offers_range)

    if success_status:
        qs = _apply_success_status(qs, success_status)

    return qs


def _apply_offers_range(qs, rng):
    if rng == "0":
        return qs.filter(offers_count=0)
    if rng == "1-5":
        return qs.filter(offers_count__gte=1, offers_count__lte=5)
    if rng == "6-10":
        return qs.filter(offers_count__gte=6, offers_count__lte=10)
    if rng == "10+":
        return qs.filter(offers_count__gt=10)
    return qs


def _apply_success_status(qs, status):
    if status == "has":
        return qs.filter(success_count__gt=0)
    if status == "none":
        return qs.filter(offers_count__gt=0, success_count=0)
    if status == "no_offers":
        return qs.filter(offers_count=0)
    return qs
