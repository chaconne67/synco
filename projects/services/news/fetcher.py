"""RSS feed fetcher — parses feeds and creates NewsArticle rows."""

from __future__ import annotations

import logging
from calendar import timegm
from datetime import datetime, timezone as dt_tz

import feedparser
import httpx
from django.utils import timezone

from projects.models import NewsArticle, NewsSource, NewsSourceType

logger = logging.getLogger(__name__)

MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5MB


def fetch_articles(source: NewsSource) -> tuple[int, int]:
    """Fetch RSS articles from a source. Returns (created, skipped).

    Only processes RSS type sources. Non-RSS sources return (0, 0).
    Uses httpx for HTTP fetch (I-R1-03), then feedparser for parsing.
    Stores raw_content from RSS entry summary/description (I-R1-08).
    """
    if source.type != NewsSourceType.RSS:
        logger.info("Skipping non-RSS source: %s (type=%s)", source.name, source.type)
        return 0, 0

    # I-R1-03: Use httpx for HTTP fetch with timeout, redirect limit, size cap
    try:
        response = httpx.get(
            source.url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "synco-news-fetcher/1.0"},
        )
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_SIZE:
            logger.warning(
                "Response too large for %s: %d bytes",
                source.name,
                len(response.content),
            )
            return 0, 0
        feed = feedparser.parse(response.text)
    except httpx.HTTPError:
        logger.exception("HTTP error fetching %s", source.name)
        return 0, 0

    if feed.bozo:
        logger.warning("Bozo feed for %s: %s", source.name, feed.bozo_exception)

    created = 0
    skipped = 0

    for entry in feed.entries:
        url = entry.link
        if not url:
            continue

        title = entry.title or ""
        if len(title) > 500:
            title = title[:497] + "..."

        published_at = _parse_published(entry)

        # I-R1-08: Store raw RSS entry summary/description in raw_content
        raw_content = entry.get("summary", "") or entry.get("description", "")

        _, was_created = NewsArticle.objects.get_or_create(
            url=url,
            defaults={
                "source": source,
                "title": title,
                "published_at": published_at,
                "raw_content": raw_content,
            },
        )

        if was_created:
            created += 1
        else:
            skipped += 1

    # Update last_fetched_at
    source.last_fetched_at = timezone.now()
    source.save(update_fields=["last_fetched_at", "updated_at"])

    logger.info("Fetched %s: %d created, %d skipped", source.name, created, skipped)
    return created, skipped


def _parse_published(entry) -> datetime | None:
    """Parse published date from feed entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.fromtimestamp(timegm(entry.published_parsed), tz=dt_tz.utc)
        except (ValueError, OverflowError):
            pass
    return None
