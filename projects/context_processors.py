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


def has_new_news(request):
    """Inject has_new_news flag for sidebar dot indicator.

    I-R1-07: Query via NewsArticleRelevance + user's assigned projects.
    Use created_at (not published_at) since published_at can be null.
    """
    if not request.user.is_authenticated:
        return {}

    try:
        membership = request.user.membership
    except Exception:
        return {}

    from projects.models import NewsArticle, SummaryStatus

    last_seen = request.user.last_news_seen_at
    if last_seen is None:
        # Never visited — check if any news exists for this org
        has_new = NewsArticle.objects.filter(
            source__organization=membership.organization,
            summary_status=SummaryStatus.COMPLETED,
        ).exists()
    else:
        # I-R1-07: Use created_at for comparison (published_at can be null)
        has_new = NewsArticle.objects.filter(
            source__organization=membership.organization,
            summary_status=SummaryStatus.COMPLETED,
            created_at__gt=last_seen,
        ).exists()

    return {"has_new_news": has_new}
