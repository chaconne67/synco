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
    *,
    categories=None,
    sizes=None,
    regions=None,
    offers_range=None,
    success_status=None,
):
    base = Client.objects.all()
    qs = base.annotate(
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
    ).order_by("-created_at")

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


def category_counts():
    """카테고리 enum name -> 건수. 0건도 포함."""
    counts = {c.name: 0 for c in IndustryCategory}
    base = Client.objects.all()
    qs = base.values("industry").annotate(n=Count("id"))
    value_to_name = {c.value: c.name for c in IndustryCategory}
    for row in qs:
        name = value_to_name.get(row["industry"])
        if name:
            counts[name] = row["n"]
    return counts


def available_regions():
    """사용 중인 region 값 리스트(가나다 순)."""
    base = Client.objects.all()
    return sorted(set(v for v in base.values_list("region", flat=True) if v))


def client_stats(client):
    """단일 고객사의 카드 통계 (리스트용과 동일 집계)."""
    one = list_clients_with_stats().filter(pk=client.pk).first()
    if not one:
        return {"offers": 0, "success": 0, "active": 0, "placed": 0}
    return {
        "offers": one.offers_count,
        "success": one.success_count,
        "active": one.active_count,
        "placed": one.placed_count,
    }


def client_projects(client, *, status_filter="all"):
    qs = client.projects.all().order_by("-created_at")
    if status_filter == "active":
        return qs.filter(status="open")
    if status_filter == "closed":
        return qs.filter(status="closed")
    return qs
