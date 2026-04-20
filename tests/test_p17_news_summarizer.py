"""P17: Gemini summarizer service tests."""

import pytest
from unittest.mock import patch, MagicMock

from projects.models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    SummaryStatus)
from projects.services.news.summarizer import summarize_article



@pytest.fixture
def source(db):
    return NewsSource.objects.create(
        name="Test Feed",
        url="https://example.com/feed.xml",
        type=NewsSourceType.RSS,
        category=NewsCategory.HIRING)


@pytest.fixture
def article(source):
    return NewsArticle.objects.create(
        source=source,
        title="AI 채용 시장 동향",
        url="https://example.com/ai-hiring",
        raw_content="AI가 채용 시장을 변화시키고 있다는 내용의 기사입니다.",
        summary_status=SummaryStatus.PENDING)


class TestSummarizeArticle:
    @patch("projects.services.news.summarizer._get_gemini_client")
    @patch("projects.services.news.summarizer.parse_llm_json")
    def test_successful_summarization(self, mock_parse_json, mock_client_fn, article):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"summary": "AI가 채용 시장을 변화시키고 있습니다.", "tags": ["AI", "채용"], "category": "hiring"}'
        mock_client.models.generate_content.return_value = mock_response
        mock_parse_json.return_value = {
            "summary": "AI가 채용 시장을 변화시키고 있습니다.",
            "tags": ["AI", "채용"],
            "category": "hiring",
        }

        result = summarize_article(article)

        assert result is True
        article.refresh_from_db()
        assert article.summary == "AI가 채용 시장을 변화시키고 있습니다."
        assert article.tags == ["AI", "채용"]
        assert article.category == NewsCategory.HIRING
        assert article.summary_status == SummaryStatus.COMPLETED

    @patch("projects.services.news.summarizer._get_gemini_client")
    def test_api_failure_marks_failed(self, mock_client_fn, article):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("API error")

        result = summarize_article(article)

        assert result is False
        article.refresh_from_db()
        assert article.summary_status == SummaryStatus.FAILED

    @patch("projects.services.news.summarizer._get_gemini_client")
    @patch("projects.services.news.summarizer.parse_llm_json")
    def test_invalid_json_marks_failed(self, mock_parse_json, mock_client_fn, article):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_client.models.generate_content.return_value = mock_response
        mock_parse_json.return_value = None  # parse_llm_json returns None on failure

        result = summarize_article(article)

        assert result is False
        article.refresh_from_db()
        assert article.summary_status == SummaryStatus.FAILED

    @patch("projects.services.news.summarizer._get_gemini_client")
    @patch("projects.services.news.summarizer.parse_llm_json")
    def test_invalid_category_defaults_to_blank(
        self, mock_parse_json, mock_client_fn, article
    ):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = (
            '{"summary": "Summary text", "tags": [], "category": "invalid_category"}'
        )
        mock_client.models.generate_content.return_value = mock_response
        mock_parse_json.return_value = {
            "summary": "Summary text",
            "tags": [],
            "category": "invalid_category",
        }

        result = summarize_article(article)

        assert result is True
        article.refresh_from_db()
        assert article.category == ""

    @patch("projects.services.news.summarizer._get_gemini_client")
    def test_skips_already_completed(self, mock_client_fn, source):
        article = NewsArticle.objects.create(
            source=source,
            title="Already done",
            url="https://example.com/done",
            summary_status=SummaryStatus.COMPLETED,
            summary="Already summarized")
        result = summarize_article(article)
        assert result is True
        mock_client_fn.assert_not_called()
