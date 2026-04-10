"""P17: RSS fetcher service tests."""

import pytest
from datetime import datetime, timezone as dt_tz
from unittest.mock import patch, MagicMock

from accounts.models import Organization
from projects.models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    SummaryStatus,
)
from projects.services.news.fetcher import fetch_articles


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def source(org):
    return NewsSource.objects.create(
        organization=org,
        name="Test Feed",
        url="https://example.com/feed.xml",
        type=NewsSourceType.RSS,
        category=NewsCategory.HIRING,
    )


def _make_feed_entry(title, link, published=None):
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.get.return_value = ""  # For summary/description
    if published:
        entry.published_parsed = published.timetuple()
    else:
        entry.published_parsed = None
    return entry


def _mock_httpx_response(text=""):
    resp = MagicMock()
    resp.text = text
    resp.content = text.encode()
    resp.raise_for_status = MagicMock()
    return resp


class TestFetchArticles:
    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.fetcher.httpx.get")
    def test_creates_new_articles(self, mock_httpx_get, mock_parse, source):
        mock_httpx_get.return_value = _mock_httpx_response("<rss/>")
        mock_parse.return_value.entries = [
            _make_feed_entry("Article 1", "https://example.com/1"),
            _make_feed_entry("Article 2", "https://example.com/2"),
        ]
        mock_parse.return_value.bozo = False

        created, skipped = fetch_articles(source)
        assert created == 2
        assert skipped == 0
        assert NewsArticle.objects.filter(source=source).count() == 2

    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.fetcher.httpx.get")
    def test_skips_existing_urls(self, mock_httpx_get, mock_parse, source):
        NewsArticle.objects.create(
            source=source, title="Existing", url="https://example.com/1"
        )
        mock_httpx_get.return_value = _mock_httpx_response("<rss/>")
        mock_parse.return_value.entries = [
            _make_feed_entry("Article 1", "https://example.com/1"),
            _make_feed_entry("Article 2", "https://example.com/2"),
        ]
        mock_parse.return_value.bozo = False

        created, skipped = fetch_articles(source)
        assert created == 1
        assert skipped == 1

    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.fetcher.httpx.get")
    def test_new_articles_have_pending_status(self, mock_httpx_get, mock_parse, source):
        mock_httpx_get.return_value = _mock_httpx_response("<rss/>")
        mock_parse.return_value.entries = [
            _make_feed_entry("New Article", "https://example.com/new"),
        ]
        mock_parse.return_value.bozo = False

        fetch_articles(source)
        article = NewsArticle.objects.get(url="https://example.com/new")
        assert article.summary_status == SummaryStatus.PENDING
        assert article.summary == ""

    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.fetcher.httpx.get")
    def test_parses_published_date(self, mock_httpx_get, mock_parse, source):
        pub_time = datetime(2026, 4, 10, 8, 0, 0, tzinfo=dt_tz.utc)
        mock_httpx_get.return_value = _mock_httpx_response("<rss/>")
        mock_parse.return_value.entries = [
            _make_feed_entry("Dated Article", "https://example.com/dated", pub_time),
        ]
        mock_parse.return_value.bozo = False

        fetch_articles(source)
        article = NewsArticle.objects.get(url="https://example.com/dated")
        assert article.published_at is not None

    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.fetcher.httpx.get")
    def test_handles_bozo_feed(self, mock_httpx_get, mock_parse, source):
        """Malformed feed should still process valid entries."""
        mock_httpx_get.return_value = _mock_httpx_response("<rss/>")
        mock_parse.return_value.entries = [
            _make_feed_entry("Still works", "https://example.com/bozo"),
        ]
        mock_parse.return_value.bozo = True

        created, skipped = fetch_articles(source)
        assert created == 1

    @patch("projects.services.news.fetcher.httpx.get")
    def test_skips_non_rss_source(self, mock_httpx_get, org):
        yt_source = NewsSource.objects.create(
            organization=org,
            name="YouTube",
            url="https://youtube.com/@channel",
            type=NewsSourceType.YOUTUBE,
            category=NewsCategory.INDUSTRY,
        )
        created, skipped = fetch_articles(yt_source)
        assert created == 0
        assert skipped == 0
        mock_httpx_get.assert_not_called()
