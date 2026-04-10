"""P17: fetch_news management command tests."""

import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from django.core.management import call_command

from accounts.models import Membership, Organization, User
from projects.models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    SummaryStatus,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def source(org):
    return NewsSource.objects.create(
        organization=org,
        name="Test Feed",
        url="https://example.com/feed.xml",
        type=NewsSourceType.RSS,
        category=NewsCategory.HIRING,
        is_active=True,
    )


class TestFetchNewsCommand:
    @patch("projects.services.news.fetcher.httpx.get")
    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.summarizer._get_gemini_client")
    @patch("projects.services.news.summarizer.parse_llm_json")
    def test_full_pipeline(
        self, mock_parse_json, mock_gemini, mock_feedparse, mock_httpx_get, source
    ):
        # Setup httpx mock
        mock_resp = MagicMock()
        mock_resp.text = "<rss/>"
        mock_resp.content = b"<rss/>"
        mock_resp.raise_for_status = MagicMock()
        mock_httpx_get.return_value = mock_resp

        # Setup RSS mock
        entry = MagicMock()
        entry.title = "Test Article"
        entry.link = "https://example.com/test-article"
        entry.get.return_value = ""
        entry.published_parsed = None
        mock_feedparse.return_value.entries = [entry]
        mock_feedparse.return_value.bozo = False

        # Setup Gemini mock
        mock_client = MagicMock()
        mock_gemini.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = (
            '{"summary": "요약입니다.", "tags": ["테스트"], "category": "hiring"}'
        )
        mock_client.models.generate_content.return_value = mock_response
        mock_parse_json.return_value = {
            "summary": "요약입니다.",
            "tags": ["테스트"],
            "category": "hiring",
        }

        out = StringIO()
        call_command("fetch_news", stdout=out)
        output = out.getvalue()

        assert "Fetching" in output or "Done" in output
        article = NewsArticle.objects.get(url="https://example.com/test-article")
        assert article.summary_status == SummaryStatus.COMPLETED

    @patch("projects.services.news.fetcher.httpx.get")
    def test_skips_inactive_sources(self, mock_httpx_get, source):
        source.is_active = False
        source.save()

        out = StringIO()
        call_command("fetch_news", stdout=out)
        mock_httpx_get.assert_not_called()

    @patch("projects.services.news.fetcher.httpx.get")
    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.summarizer._get_gemini_client")
    @patch("projects.services.news.summarizer.parse_llm_json")
    def test_retries_failed_articles(
        self, mock_parse_json, mock_gemini, mock_feedparse, mock_httpx_get, source
    ):
        # Create a failed article
        NewsArticle.objects.create(
            source=source,
            title="Failed Article",
            url="https://example.com/failed",
            summary_status=SummaryStatus.FAILED,
        )

        # Setup httpx mock
        mock_resp = MagicMock()
        mock_resp.text = "<rss/>"
        mock_resp.content = b"<rss/>"
        mock_resp.raise_for_status = MagicMock()
        mock_httpx_get.return_value = mock_resp

        mock_feedparse.return_value.entries = []
        mock_feedparse.return_value.bozo = False

        # Setup Gemini mock for retry
        mock_client = MagicMock()
        mock_gemini.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = (
            '{"summary": "재시도 성공.", "tags": ["테스트"], "category": "hr"}'
        )
        mock_client.models.generate_content.return_value = mock_response
        mock_parse_json.return_value = {
            "summary": "재시도 성공.",
            "tags": ["테스트"],
            "category": "hr",
        }

        call_command("fetch_news")
        article = NewsArticle.objects.get(url="https://example.com/failed")
        assert article.summary_status == SummaryStatus.COMPLETED
