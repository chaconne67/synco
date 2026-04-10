"""P17: News feed views."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Membership, Organization

from .forms import NewsSourceForm
from .models import (
    NewsArticle,
    NewsArticleRelevance,
    NewsCategory,
    NewsSource,
    SummaryStatus,
)


def _get_org(request) -> Organization:
    return get_object_or_404(Organization, memberships__user=request.user)


def _is_staff(request) -> bool:
    """Check if user has staff-level access (owner role)."""
    try:
        return request.user.membership.role in ("owner",)
    except Membership.DoesNotExist:
        return False


@login_required
def news_feed(request):
    """News feed main page."""
    org = _get_org(request)

    # My project-related news (via relevance join)
    my_projects = request.user.assigned_projects.filter(organization=org)
    related_articles = (
        NewsArticle.objects.filter(
            relevances__project__in=my_projects,
            summary_status=SummaryStatus.COMPLETED,
        )
        .distinct()
        .order_by("-published_at")[:10]
    )

    # All org news
    all_articles = (
        NewsArticle.objects.filter(
            source__organization=org,
            summary_status=SummaryStatus.COMPLETED,
        )
        .order_by("-published_at")[:50]
    )

    # Update last_news_seen_at
    request.user.last_news_seen_at = timezone.now()
    request.user.save(update_fields=["last_news_seen_at"])

    categories = NewsCategory.choices

    return render(
        request,
        "projects/news_feed.html",
        {
            "related_articles": related_articles,
            "all_articles": all_articles,
            "categories": categories,
            "active_category": "",
            "is_staff": _is_staff(request),
        },
    )


@login_required
def news_filter(request):
    """HTMX partial: filter articles by category."""
    org = _get_org(request)
    category = request.GET.get("category", "")

    articles = NewsArticle.objects.filter(
        source__organization=org,
        summary_status=SummaryStatus.COMPLETED,
    )

    if category and category in dict(NewsCategory.choices):
        articles = articles.filter(category=category)

    articles = articles.order_by("-published_at")[:50]

    return render(
        request,
        "projects/partials/news_list.html",
        {"articles": articles, "active_category": category},
    )


@login_required
def news_sources(request):
    """Source management list page."""
    if not _is_staff(request):
        return HttpResponse(status=403)

    org = _get_org(request)
    sources = NewsSource.objects.filter(organization=org)

    return render(
        request,
        "projects/news_sources.html",
        {"sources": sources},
    )


@login_required
def news_source_create(request):
    """Create a new news source."""
    if not _is_staff(request):
        return HttpResponse(status=403)

    org = _get_org(request)

    if request.method == "POST":
        form = NewsSourceForm(request.POST)
        if form.is_valid():
            source = form.save(commit=False)
            source.organization = org
            source.save()
            return redirect("news:news_sources")
    else:
        form = NewsSourceForm()

    return render(
        request,
        "projects/news_source_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def news_source_update(request, pk):
    """Edit an existing news source."""
    if not _is_staff(request):
        return HttpResponse(status=403)

    org = _get_org(request)
    source = get_object_or_404(NewsSource, pk=pk, organization=org)

    if request.method == "POST":
        form = NewsSourceForm(request.POST, instance=source)
        if form.is_valid():
            form.save()
            return redirect("news:news_sources")
    else:
        form = NewsSourceForm(instance=source)

    return render(
        request,
        "projects/news_source_form.html",
        {"form": form, "is_edit": True, "source": source},
    )


@login_required
@require_POST
def news_source_delete(request, pk):
    """Delete a news source."""
    if not _is_staff(request):
        return HttpResponse(status=403)

    org = _get_org(request)
    source = get_object_or_404(NewsSource, pk=pk, organization=org)
    source.delete()
    return redirect("news:news_sources")


@login_required
@require_POST
def news_source_toggle(request, pk):
    """Toggle source active/inactive."""
    if not _is_staff(request):
        return HttpResponse(status=403)

    org = _get_org(request)
    source = get_object_or_404(NewsSource, pk=pk, organization=org)
    source.is_active = not source.is_active
    source.save(update_fields=["is_active", "updated_at"])
    return redirect("news:news_sources")
