"""P17: News feed views."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import level_required
from accounts.helpers import _get_org

from .forms import NewsSourceForm
from .models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    SummaryStatus,
)


@login_required
@level_required(1)
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
    all_articles = NewsArticle.objects.filter(
        source__organization=org,
        summary_status=SummaryStatus.COMPLETED,
    ).order_by("-published_at")[:50]

    # Update last_news_seen_at
    request.user.last_news_seen_at = timezone.now()
    request.user.save(update_fields=["last_news_seen_at"])

    categories = NewsCategory.choices
    is_staff = request.user.is_superuser or request.user.level >= 2

    return render(
        request,
        "projects/news_feed.html",
        {
            "related_articles": related_articles,
            "all_articles": all_articles,
            "categories": categories,
            "active_category": "",
            "is_staff": is_staff,
        },
    )


@login_required
@level_required(1)
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
@level_required(2)
def news_sources(request):
    """Source management list page."""
    org = _get_org(request)
    sources = NewsSource.objects.filter(organization=org)

    return render(
        request,
        "projects/news_sources.html",
        {"sources": sources},
    )


@login_required
@level_required(2)
def news_source_create(request):
    """Create a new news source."""
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
@level_required(2)
def news_source_update(request, pk):
    """Edit an existing news source."""
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
@level_required(2)
def news_source_delete(request, pk):
    """Delete a news source."""
    org = _get_org(request)
    source = get_object_or_404(NewsSource, pk=pk, organization=org)
    source.delete()
    return redirect("news:news_sources")


@login_required
@require_POST
@level_required(2)
def news_source_toggle(request, pk):
    """Toggle source active/inactive."""
    org = _get_org(request)
    source = get_object_or_404(NewsSource, pk=pk, organization=org)
    source.is_active = not source.is_active
    source.save(update_fields=["is_active", "updated_at"])
    return redirect("news:news_sources")
