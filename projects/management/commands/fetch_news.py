"""fetch_news — daily news pipeline: fetch → summarize → match → notify."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import TelegramBinding
from projects.models import (
    NewsArticle,
    NewsArticleRelevance,
    NewsSource,
    NewsSourceType,
    Notification,
    SummaryStatus,
)
from projects.services.news.fetcher import fetch_articles
from projects.services.news.matcher import match_article
from projects.services.news.summarizer import summarize_article
from projects.services.notification import send_notification

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch news articles, summarize with AI, match to projects, notify via Telegram."

    def handle(self, *args, **options):
        self.stdout.write("Fetching news...")

        # Phase 1: Fetch RSS articles from all active sources
        sources = NewsSource.objects.filter(is_active=True, type=NewsSourceType.RSS)
        total_created = 0
        total_skipped = 0

        for source in sources:
            try:
                created, skipped = fetch_articles(source)
                total_created += created
                total_skipped += skipped
            except Exception:
                logger.exception("Failed to fetch source: %s", source.name)

        self.stdout.write(f"  Fetch: {total_created} new, {total_skipped} existing")

        # Phase 2: Summarize pending + retry failed articles
        pending_articles = NewsArticle.objects.filter(
            summary_status__in=[SummaryStatus.PENDING, SummaryStatus.FAILED]
        )
        summarized = 0
        failed = 0

        for article in pending_articles:
            success = summarize_article(article)
            if success:
                summarized += 1
            else:
                failed += 1

        self.stdout.write(f"  Summarize: {summarized} done, {failed} failed")

        # Phase 3: Match summarized articles to projects
        cutoff = timezone.now() - timedelta(hours=24)
        recent_articles = NewsArticle.objects.filter(
            summary_status=SummaryStatus.COMPLETED,
            updated_at__gte=cutoff,
        )
        total_matches = 0

        for article in recent_articles:
            total_matches += match_article(article)

        self.stdout.write(f"  Match: {total_matches} project-article links")

        # Phase 4: Telegram digest (per recipient, I-R1-04)
        self._send_digests(cutoff)

        self.stdout.write(self.style.SUCCESS("Done."))

    def _send_digests(self, cutoff):
        """Send per-recipient news digests to Telegram-bound users.

        I-R1-04: Build per-recipient digest from NewsArticleRelevance
        (user's assigned projects), not from all org articles.
        I-R1-05: Dedup with get_or_create inside transaction.atomic().
        """
        today = timezone.now().date()

        bindings = TelegramBinding.objects.filter(
            is_active=True,
        ).select_related("user")

        sent = 0
        for binding in bindings:
            user = binding.user

            # Get user's assigned projects
            user_projects = user.assigned_projects.all()
            if not user_projects.exists():
                continue

            # Get relevant articles for user's projects
            relevances = (
                NewsArticleRelevance.objects.filter(
                    project__in=user_projects,
                    article__summary_status=SummaryStatus.COMPLETED,
                    article__updated_at__gte=cutoff,
                )
                .select_related("article")
                .order_by("-article__published_at")
                .distinct("article")[:10]
            )

            if not relevances:
                continue

            # Build digest text
            digest_lines = ["[synco] 오늘의 뉴스 요약\n"]
            for rel in relevances:
                article = rel.article
                category_display = article.get_category_display() or "기타"
                digest_lines.append(
                    f"[{category_display}] {article.title}\n{article.url}\n"
                )
            digest_text = "\n".join(digest_lines)

            # I-R1-05: Dedup with get_or_create + transaction.atomic()
            with transaction.atomic():
                notif, created = Notification.objects.get_or_create(
                    recipient=user,
                    type=Notification.Type.NEWS,
                    created_at__date=today,
                    defaults={
                        "title": "오늘의 뉴스 요약",
                        "body": digest_text,
                    },
                )

            if created:
                transaction.on_commit(
                    lambda n=notif, t=digest_text: send_notification(n, text=t)
                )
                sent += 1

        if sent:
            self.stdout.write(f"  Telegram: {sent} digests sent")
