"""Project relevance matching — scores articles against active projects."""

from __future__ import annotations

import logging

from projects.models import (
    NewsArticle,
    NewsArticleRelevance,
    Project,
    ProjectStatus,
)

logger = logging.getLogger(__name__)

# Score weights for matching criteria
WEIGHT_CLIENT_NAME = 0.9
WEIGHT_INDUSTRY = 0.6
WEIGHT_TAG_KEYWORD = 0.5
RELEVANCE_THRESHOLD = 0.5

# Statuses considered "active" for matching
ACTIVE_STATUSES = [
    ProjectStatus.OPEN,
]


def match_article(article: NewsArticle) -> int:
    """Match a single article against active projects in the same org.

    Creates/updates NewsArticleRelevance rows for matches above threshold.
    Deletes stale relevance rows below threshold or for closed projects (I-R1-08).
    Returns the number of matched projects.
    """
    if not article.source:
        return 0

    projects = Project.objects.filter(
        status__in=ACTIVE_STATUSES,
    ).select_related("client")

    matched = 0
    article_text = f"{article.title} {' '.join(article.tags)}".lower()
    matched_project_ids = set()

    for project in projects:
        score, terms = _compute_relevance(article_text, article.tags, project)

        if score >= RELEVANCE_THRESHOLD:
            NewsArticleRelevance.objects.update_or_create(
                article=article,
                project=project,
                defaults={
                    "score": round(score, 3),
                    "matched_terms": terms,
                },
            )
            matched += 1
            matched_project_ids.add(project.pk)

    # I-R1-08: Delete stale relevance rows (below threshold or closed projects)
    NewsArticleRelevance.objects.filter(article=article).exclude(
        project_id__in=matched_project_ids
    ).delete()

    logger.info("Matched article '%s' to %d projects", article.title[:50], matched)
    return matched


def _compute_relevance(
    article_text: str,
    tags: list[str],
    project: Project,
) -> tuple[float, list[str]]:
    """Compute relevance score between article and project.

    Returns (score, matched_terms).
    """
    score = 0.0
    terms: list[str] = []

    client_name = project.client.name.lower() if project.client else ""
    industry = project.client.industry.lower() if project.client else ""
    project_title = project.title.lower()

    # Client name match (highest weight)
    if client_name and client_name in article_text:
        score = max(score, WEIGHT_CLIENT_NAME)
        terms.append(f"client:{project.client.name}")

    # Industry match
    if industry and industry in article_text:
        score = max(score, WEIGHT_INDUSTRY)
        terms.append(f"industry:{project.client.industry}")

    # Tag-based keyword matching against project title
    tag_lower = [t.lower() for t in tags]
    title_words = set(project_title.split())
    for tag in tag_lower:
        if tag in project_title or any(tag in w for w in title_words):
            score = max(score, WEIGHT_TAG_KEYWORD)
            terms.append(f"tag:{tag}")

    return score, terms
