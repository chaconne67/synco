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

    from projects.models import NewsArticleRelevance, SummaryStatus

    # I-R1-07: Query via NewsArticleRelevance + user's assigned projects
    user_projects = request.user.assigned_projects.filter(
        organization=membership.organization
    )
    if not user_projects.exists():
        return {"has_new_news": False}

    last_seen = request.user.last_news_seen_at
    if last_seen is None:
        # Never visited — check if any relevant news exists
        has_new = NewsArticleRelevance.objects.filter(
            project__in=user_projects,
            article__summary_status=SummaryStatus.COMPLETED,
        ).exists()
    else:
        # I-R1-07: Use created_at for comparison (published_at can be null)
        has_new = NewsArticleRelevance.objects.filter(
            project__in=user_projects,
            article__summary_status=SummaryStatus.COMPLETED,
            article__created_at__gt=last_seen,
        ).exists()

    return {"has_new_news": has_new}
