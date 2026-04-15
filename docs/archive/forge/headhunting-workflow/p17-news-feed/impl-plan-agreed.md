# P17 News Feed — 확정 구현계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a news feed feature that fetches RSS articles, summarizes them with Gemini AI, matches them to headhunting projects by relevance, and delivers daily digests via Telegram.

**Architecture:** Three new models (NewsSource, NewsArticle, NewsArticleRelevance) in the projects app. A management command orchestrates the pipeline: RSS fetch → Gemini summarize → relevance match → Telegram notify. HTMX-powered UI for feed browsing and source management.

**Tech Stack:** Django 5.2, feedparser, httpx, google-genai, HTMX, Tailwind CSS, PostgreSQL

## Tempering Amendments (구현담금질 반영 사항)

The following changes from implementation tempering MUST be applied during implementation:

1. **I-R1-02 [CRITICAL]:** `NewsArticle.source` FK uses `on_delete=models.SET_NULL, null=True, blank=True` instead of `CASCADE`. Source deletion must NOT cascade-delete articles.
2. **I-R1-03:** Fetcher must use `httpx` for HTTP fetch with `timeout=30`, `max_redirects=5`, response size cap (5MB), then pass content to `feedparser.parse()` instead of `feedparser.parse(url)` directly.
3. **I-R1-04:** `_send_digests` must build per-recipient digest from `NewsArticleRelevance` (user's assigned projects), not from all org articles.
4. **I-R1-05:** Notification dedup must use `get_or_create` inside `transaction.atomic()` instead of `exists()` + `create()`.
5. **I-R1-06:** Add Task 10 (Deployment) with crontab file creation and smoke test.
6. **I-R1-07:** Context processor `has_new_news` must query via `NewsArticleRelevance` + user's assigned projects, not all org news. Use `created_at` (not `published_at`) for comparison since `published_at` can be null.
7. **I-R1-08:** Matcher must delete stale `NewsArticleRelevance` rows (below threshold or closed projects) before creating new ones.
8. **I-R1-09:** Add `raw_content = models.TextField(blank=True)` to `NewsArticle`. Fetcher stores RSS entry `summary`/`description` in `raw_content`. Summarizer sends `raw_content` as input to Gemini (not `article.summary`).
9. **I-R1-14:** Summarizer must use `parse_llm_json` from `data_extraction.services.extraction.sanitizers` instead of plain `json.loads()`.
10. **I-R1-13:** Test `test_non_staff_blocked_from_source_crud` must assert exact `403` status code.

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `projects/models.py` | Add NewsSource, NewsArticle, NewsArticleRelevance models + TextChoices | Modify |
| `accounts/models.py` | Add `last_news_seen_at` field to User | Modify |
| `projects/urls_news.py` | News URL routing (top-level `/news/`) | Create |
| `main/urls.py` | Register news URL mount | Modify |
| `projects/views_news.py` | News feed views + source CRUD | Create |
| `projects/forms.py` | Add NewsSourceForm | Modify |
| `projects/services/news/__init__.py` | Package init | Create |
| `projects/services/news/fetcher.py` | RSS parsing + article creation | Create |
| `projects/services/news/summarizer.py` | Gemini API summarization | Create |
| `projects/services/news/matcher.py` | Project relevance matching | Create |
| `projects/management/commands/fetch_news.py` | Pipeline orchestration command | Create |
| `projects/context_processors.py` | Add news dot indicator | Modify |
| `templates/common/nav_sidebar.html` | Add news menu item | Modify |
| `projects/templates/projects/news_feed.html` | News feed main page | Create |
| `projects/templates/projects/partials/news_list.html` | News article list partial (HTMX) | Create |
| `projects/templates/projects/news_sources.html` | Source management page | Create |
| `projects/templates/projects/news_source_form.html` | Source create/edit form | Create |
| `tests/test_p17_news_models.py` | Model tests | Create |
| `tests/test_p17_news_fetcher.py` | Fetcher service tests | Create |
| `tests/test_p17_news_summarizer.py` | Summarizer service tests | Create |
| `tests/test_p17_news_matcher.py` | Matcher service tests | Create |
| `tests/test_p17_news_views.py` | View tests | Create |
| `tests/test_p17_news_command.py` | Management command tests | Create |

---

### Task 1: Add feedparser dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add feedparser to dependencies**

```bash
uv add feedparser
```

- [ ] **Step 2: Verify installation**

```bash
uv run python -c "import feedparser; print(feedparser.__version__)"
```

Expected: Version number printed without error.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps(p17): add feedparser for RSS parsing"
```

---

### Task 2: Models + Migration

**Files:**
- Modify: `projects/models.py`
- Modify: `accounts/models.py`
- Create: `tests/test_p17_news_models.py`

- [ ] **Step 1: Write model tests**

```python
# tests/test_p17_news_models.py
"""P17: News feed model tests."""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import Membership, Organization, User
from projects.models import (
    NewsArticle,
    NewsArticleRelevance,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    Project,
    SummaryStatus,
)
from clients.models import Client


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def client_co(org):
    return Client.objects.create(name="Acme Corp", organization=org)


@pytest.fixture
def project(org, client_co, user):
    return Project.objects.create(
        organization=org, client=client_co, title="Backend Dev", created_by=user
    )


@pytest.fixture
def news_source(org):
    return NewsSource.objects.create(
        organization=org,
        name="TechCrunch Korea",
        url="https://techcrunch.com/feed/",
        type=NewsSourceType.RSS,
        category=NewsCategory.INDUSTRY,
    )


@pytest.fixture
def news_article(news_source):
    return NewsArticle.objects.create(
        source=news_source,
        title="AI Hiring Trends 2026",
        url="https://example.com/article-1",
        published_at=timezone.now(),
        summary_status=SummaryStatus.COMPLETED,
        summary="AI is transforming hiring.",
        category=NewsCategory.HIRING,
        tags=["AI", "채용"],
    )


class TestNewsSource:
    def test_create_source(self, news_source):
        assert news_source.is_active is True
        assert news_source.type == NewsSourceType.RSS
        assert news_source.last_fetched_at is None
        assert news_source.id is not None  # UUID PK from BaseModel

    def test_source_str(self, news_source):
        assert str(news_source) == "TechCrunch Korea"

    def test_source_ordering(self, org):
        s1 = NewsSource.objects.create(
            organization=org, name="A", url="https://a.com/feed", category=NewsCategory.HR
        )
        s2 = NewsSource.objects.create(
            organization=org, name="B", url="https://b.com/feed", category=NewsCategory.HR
        )
        sources = list(NewsSource.objects.all())
        # ordering = ["-created_at"], so s2 (newer) comes first
        assert sources[0] == s2


class TestNewsArticle:
    def test_create_article(self, news_article):
        assert news_article.id is not None
        assert news_article.summary_status == SummaryStatus.COMPLETED

    def test_unique_url_constraint(self, news_source):
        NewsArticle.objects.create(
            source=news_source, title="A", url="https://example.com/dup"
        )
        with pytest.raises(IntegrityError):
            NewsArticle.objects.create(
                source=news_source, title="B", url="https://example.com/dup"
            )

    def test_default_summary_status(self, news_source):
        article = NewsArticle.objects.create(
            source=news_source, title="New", url="https://example.com/new"
        )
        assert article.summary_status == SummaryStatus.PENDING

    def test_cascade_delete_source(self, news_article, news_source):
        article_id = news_article.id
        news_source.delete()
        assert not NewsArticle.objects.filter(id=article_id).exists()


class TestNewsArticleRelevance:
    def test_create_relevance(self, news_article, project):
        rel = NewsArticleRelevance.objects.create(
            article=news_article, project=project, score=0.85, matched_terms=["AI"]
        )
        assert rel.score == 0.85
        assert rel.matched_terms == ["AI"]

    def test_unique_article_project(self, news_article, project):
        NewsArticleRelevance.objects.create(
            article=news_article, project=project, score=0.8
        )
        with pytest.raises(IntegrityError):
            NewsArticleRelevance.objects.create(
                article=news_article, project=project, score=0.9
            )

    def test_cascade_delete_project(self, news_article, project):
        rel = NewsArticleRelevance.objects.create(
            article=news_article, project=project, score=0.8
        )
        rel_id = rel.id
        project.delete()
        assert not NewsArticleRelevance.objects.filter(id=rel_id).exists()

    def test_cascade_delete_article(self, news_article, project):
        rel = NewsArticleRelevance.objects.create(
            article=news_article, project=project, score=0.8
        )
        rel_id = rel.id
        news_article.delete()
        assert not NewsArticleRelevance.objects.filter(id=rel_id).exists()


class TestUserLastNewsSeen:
    def test_last_news_seen_at_default_null(self, user):
        user.refresh_from_db()
        assert user.last_news_seen_at is None

    def test_set_last_news_seen_at(self, user):
        now = timezone.now()
        user.last_news_seen_at = now
        user.save(update_fields=["last_news_seen_at"])
        user.refresh_from_db()
        assert user.last_news_seen_at == now
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_p17_news_models.py -v
```

Expected: ImportError or model-not-found errors.

- [ ] **Step 3: Add models to projects/models.py**

Append to the end of `projects/models.py`:

```python
class NewsSourceType(models.TextChoices):
    RSS = "rss", "RSS/뉴스"
    YOUTUBE = "youtube", "YouTube"
    BLOG = "blog", "블로그"


class NewsCategory(models.TextChoices):
    HIRING = "hiring", "채용"
    HR = "hr", "인사"
    INDUSTRY = "industry", "업계동향"
    ECONOMY = "economy", "경제/실업"


class SummaryStatus(models.TextChoices):
    PENDING = "pending", "대기"
    COMPLETED = "completed", "완료"
    FAILED = "failed", "실패"


class NewsSource(BaseModel):
    """뉴스 소스 (RSS 피드)."""

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="news_sources",
    )
    name = models.CharField(max_length=200)
    url = models.URLField()
    type = models.CharField(
        max_length=20,
        choices=NewsSourceType.choices,
        default=NewsSourceType.RSS,
    )
    category = models.CharField(
        max_length=20,
        choices=NewsCategory.choices,
    )
    is_active = models.BooleanField(default=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class NewsArticle(BaseModel):
    """뉴스 기사."""

    source = models.ForeignKey(
        NewsSource,
        on_delete=models.CASCADE,
        related_name="articles",
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    url = models.URLField(unique=True)
    published_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    category = models.CharField(
        max_length=20,
        choices=NewsCategory.choices,
        blank=True,
    )
    summary_status = models.CharField(
        max_length=20,
        choices=SummaryStatus.choices,
        default=SummaryStatus.PENDING,
    )

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.title


class NewsArticleRelevance(BaseModel):
    """기사-프로젝트 관련도 (정규화 조인 모델)."""

    article = models.ForeignKey(
        NewsArticle,
        on_delete=models.CASCADE,
        related_name="relevances",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="news_relevances",
    )
    score = models.FloatField()
    matched_terms = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "project"],
                name="unique_article_project_relevance",
            )
        ]

    def __str__(self) -> str:
        return f"{self.article.title} -> {self.project.title} ({self.score:.2f})"
```

- [ ] **Step 4: Add `last_news_seen_at` to User model in `accounts/models.py`**

Add this field to the `User` class after the `updated_at` field:

```python
    last_news_seen_at = models.DateTimeField(null=True, blank=True)
```

- [ ] **Step 5: Create and apply migrations**

```bash
uv run python manage.py makemigrations projects accounts
uv run python manage.py migrate
```

- [ ] **Step 6: Run model tests**

```bash
uv run pytest tests/test_p17_news_models.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add projects/models.py accounts/models.py projects/migrations/ accounts/migrations/ tests/test_p17_news_models.py
git commit -m "feat(p17): add NewsSource, NewsArticle, NewsArticleRelevance models"
```

---

### Task 3: Fetcher Service

**Files:**
- Create: `projects/services/news/__init__.py`
- Create: `projects/services/news/fetcher.py`
- Create: `tests/test_p17_news_fetcher.py`

- [ ] **Step 1: Create package init**

```python
# projects/services/news/__init__.py
```

Empty file.

- [ ] **Step 2: Write fetcher tests**

```python
# tests/test_p17_news_fetcher.py
"""P17: RSS fetcher service tests."""

import pytest
from datetime import datetime, timezone as dt_tz
from unittest.mock import patch, MagicMock

from accounts.models import Membership, Organization, User
from projects.models import NewsArticle, NewsCategory, NewsSource, NewsSourceType, SummaryStatus
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


class TestFetchArticles:
    @patch("projects.services.news.fetcher.feedparser.parse")
    def test_creates_new_articles(self, mock_parse, source):
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
    def test_skips_existing_urls(self, mock_parse, source):
        NewsArticle.objects.create(
            source=source, title="Existing", url="https://example.com/1"
        )
        mock_parse.return_value.entries = [
            _make_feed_entry("Article 1", "https://example.com/1"),
            _make_feed_entry("Article 2", "https://example.com/2"),
        ]
        mock_parse.return_value.bozo = False

        created, skipped = fetch_articles(source)
        assert created == 1
        assert skipped == 1

    @patch("projects.services.news.fetcher.feedparser.parse")
    def test_new_articles_have_pending_status(self, mock_parse, source):
        mock_parse.return_value.entries = [
            _make_feed_entry("New Article", "https://example.com/new"),
        ]
        mock_parse.return_value.bozo = False

        fetch_articles(source)
        article = NewsArticle.objects.get(url="https://example.com/new")
        assert article.summary_status == SummaryStatus.PENDING
        assert article.summary == ""

    @patch("projects.services.news.fetcher.feedparser.parse")
    def test_parses_published_date(self, mock_parse, source):
        pub_time = datetime(2026, 4, 10, 8, 0, 0, tzinfo=dt_tz.utc)
        mock_parse.return_value.entries = [
            _make_feed_entry("Dated Article", "https://example.com/dated", pub_time),
        ]
        mock_parse.return_value.bozo = False

        fetch_articles(source)
        article = NewsArticle.objects.get(url="https://example.com/dated")
        assert article.published_at is not None

    @patch("projects.services.news.fetcher.feedparser.parse")
    def test_handles_bozo_feed(self, mock_parse, source):
        """Malformed feed should still process valid entries."""
        mock_parse.return_value.entries = [
            _make_feed_entry("Still works", "https://example.com/bozo"),
        ]
        mock_parse.return_value.bozo = True

        created, skipped = fetch_articles(source)
        assert created == 1

    @patch("projects.services.news.fetcher.feedparser.parse")
    def test_skips_non_rss_source(self, mock_parse, org):
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
        mock_parse.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_p17_news_fetcher.py -v
```

Expected: ImportError for `projects.services.news.fetcher`.

- [ ] **Step 4: Implement fetcher**

```python
# projects/services/news/fetcher.py
"""RSS feed fetcher — parses feeds and creates NewsArticle rows."""

from __future__ import annotations

import logging
from calendar import timegm
from datetime import datetime, timezone as dt_tz

import feedparser
from django.utils import timezone

from projects.models import NewsArticle, NewsSource, NewsSourceType

logger = logging.getLogger(__name__)

# feedparser respects this for HTTP requests
feedparser.USER_AGENT = "synco-news-fetcher/1.0"


def fetch_articles(source: NewsSource) -> tuple[int, int]:
    """Fetch RSS articles from a source. Returns (created, skipped).

    Only processes RSS type sources. Non-RSS sources return (0, 0).
    Uses get_or_create on URL for idempotency.
    """
    if source.type != NewsSourceType.RSS:
        logger.info("Skipping non-RSS source: %s (type=%s)", source.name, source.type)
        return 0, 0

    feed = feedparser.parse(source.url)

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

        _, was_created = NewsArticle.objects.get_or_create(
            url=url,
            defaults={
                "source": source,
                "title": title,
                "published_at": published_at,
            },
        )

        if was_created:
            created += 1
        else:
            skipped += 1

    # Update last_fetched_at
    source.last_fetched_at = timezone.now()
    source.save(update_fields=["last_fetched_at", "updated_at"])

    logger.info(
        "Fetched %s: %d created, %d skipped", source.name, created, skipped
    )
    return created, skipped


def _parse_published(entry) -> datetime | None:
    """Parse published date from feed entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.fromtimestamp(
                timegm(entry.published_parsed), tz=dt_tz.utc
            )
        except (ValueError, OverflowError):
            pass
    return None
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_p17_news_fetcher.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add projects/services/news/__init__.py projects/services/news/fetcher.py tests/test_p17_news_fetcher.py
git commit -m "feat(p17): add RSS fetcher service"
```

---

### Task 4: Summarizer Service

**Files:**
- Create: `projects/services/news/summarizer.py`
- Create: `tests/test_p17_news_summarizer.py`

- [ ] **Step 1: Write summarizer tests**

```python
# tests/test_p17_news_summarizer.py
"""P17: Gemini summarizer service tests."""

import pytest
from unittest.mock import patch, MagicMock

from accounts.models import Organization
from projects.models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    SummaryStatus,
)
from projects.services.news.summarizer import summarize_article


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


@pytest.fixture
def article(source):
    return NewsArticle.objects.create(
        source=source,
        title="AI 채용 시장 동향",
        url="https://example.com/ai-hiring",
        summary_status=SummaryStatus.PENDING,
    )


class TestSummarizeArticle:
    @patch("projects.services.news.summarizer._get_gemini_client")
    def test_successful_summarization(self, mock_client_fn, article):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"summary": "AI가 채용 시장을 변화시키고 있습니다.", "tags": ["AI", "채용"], "category": "hiring"}'
        mock_client.models.generate_content.return_value = mock_response

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
    def test_invalid_json_marks_failed(self, mock_client_fn, article):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_client.models.generate_content.return_value = mock_response

        result = summarize_article(article)

        assert result is False
        article.refresh_from_db()
        assert article.summary_status == SummaryStatus.FAILED

    @patch("projects.services.news.summarizer._get_gemini_client")
    def test_invalid_category_defaults_to_blank(self, mock_client_fn, article):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"summary": "Summary text", "tags": [], "category": "invalid_category"}'
        mock_client.models.generate_content.return_value = mock_response

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
            summary="Already summarized",
        )
        result = summarize_article(article)
        assert result is True
        mock_client_fn.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_p17_news_summarizer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement summarizer**

```python
# projects/services/news/summarizer.py
"""Gemini AI article summarizer — extracts summary, tags, and category."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db import transaction
from google import genai

from projects.models import NewsArticle, NewsCategory, SummaryStatus

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"

VALID_CATEGORIES = {c.value for c in NewsCategory}

SUMMARIZE_PROMPT = """You are a Korean news article summarizer for a headhunting platform.

Given an article title (and optional content), produce a JSON response with:
- "summary": 2-3 sentence summary in Korean
- "tags": list of 3-7 Korean keyword strings relevant to hiring/HR industry
- "category": exactly one of "hiring" | "hr" | "industry" | "economy"

Rules:
- category MUST be one of the four exact English strings above
- summary MUST be in Korean
- tags MUST be Korean keywords
- Respond ONLY with valid JSON, no markdown fencing

Article title: {title}
Article content: {content}"""


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def summarize_article(article: NewsArticle) -> bool:
    """Summarize a single article with Gemini AI.

    Returns True on success, False on failure.
    Skips articles that are already COMPLETED.
    Updates summary_status atomically.
    """
    if article.summary_status == SummaryStatus.COMPLETED:
        return True

    try:
        client = _get_gemini_client()
        prompt = SUMMARIZE_PROMPT.format(
            title=article.title,
            content=article.summary or "(no content available)",
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                max_output_tokens=1000,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        parsed = json.loads(response.text)

        summary = parsed.get("summary", "")
        tags = parsed.get("tags", [])
        category = parsed.get("category", "")

        if category not in VALID_CATEGORIES:
            logger.warning(
                "Invalid category '%s' for article %s, defaulting to blank",
                category,
                article.pk,
            )
            category = ""

        with transaction.atomic():
            article.summary = summary
            article.tags = tags if isinstance(tags, list) else []
            article.category = category
            article.summary_status = SummaryStatus.COMPLETED
            article.save(
                update_fields=[
                    "summary", "tags", "category", "summary_status", "updated_at"
                ]
            )

        return True

    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse Gemini response for article %s: %s", article.pk, e)
        article.summary_status = SummaryStatus.FAILED
        article.save(update_fields=["summary_status", "updated_at"])
        return False

    except Exception:
        logger.exception("Gemini API error for article %s", article.pk)
        article.summary_status = SummaryStatus.FAILED
        article.save(update_fields=["summary_status", "updated_at"])
        return False
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_p17_news_summarizer.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add projects/services/news/summarizer.py tests/test_p17_news_summarizer.py
git commit -m "feat(p17): add Gemini summarizer service"
```

---

### Task 5: Matcher Service

**Files:**
- Create: `projects/services/news/matcher.py`
- Create: `tests/test_p17_news_matcher.py`

- [ ] **Step 1: Write matcher tests**

```python
# tests/test_p17_news_matcher.py
"""P17: Project relevance matcher tests."""

import pytest
from django.utils import timezone

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import (
    NewsArticle,
    NewsArticleRelevance,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    Project,
    SummaryStatus,
)
from projects.services.news.matcher import match_article


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def client_co(org):
    return Client.objects.create(
        name="삼성전자", industry="반도체", organization=org
    )


@pytest.fixture
def project(org, client_co, user):
    return Project.objects.create(
        organization=org,
        client=client_co,
        title="반도체 설계 엔지니어",
        created_by=user,
    )


@pytest.fixture
def source(org):
    return NewsSource.objects.create(
        organization=org,
        name="Feed",
        url="https://example.com/feed",
        type=NewsSourceType.RSS,
        category=NewsCategory.HIRING,
    )


class TestMatchArticle:
    def test_matches_client_name(self, source, project):
        article = NewsArticle.objects.create(
            source=source,
            title="삼성전자 대규모 채용",
            url="https://example.com/samsung",
            tags=["삼성전자", "채용"],
            summary_status=SummaryStatus.COMPLETED,
        )
        count = match_article(article)
        assert count >= 1
        rel = NewsArticleRelevance.objects.get(article=article, project=project)
        assert rel.score >= 0.5

    def test_matches_industry(self, source, project):
        article = NewsArticle.objects.create(
            source=source,
            title="반도체 산업 전망",
            url="https://example.com/semiconductor",
            tags=["반도체", "전망"],
            summary_status=SummaryStatus.COMPLETED,
        )
        count = match_article(article)
        assert count >= 1

    def test_no_match_below_threshold(self, source, org, user):
        unrelated_client = Client.objects.create(
            name="무관회사", industry="패션", organization=org
        )
        unrelated_project = Project.objects.create(
            organization=org,
            client=unrelated_client,
            title="패션 디자이너",
            created_by=user,
        )
        article = NewsArticle.objects.create(
            source=source,
            title="의료 AI 발전",
            url="https://example.com/medical",
            tags=["의료", "AI"],
            summary_status=SummaryStatus.COMPLETED,
        )
        match_article(article)
        assert not NewsArticleRelevance.objects.filter(
            article=article, project=unrelated_project
        ).exists()

    def test_idempotent_matching(self, source, project):
        article = NewsArticle.objects.create(
            source=source,
            title="삼성전자 뉴스",
            url="https://example.com/samsung2",
            tags=["삼성전자"],
            summary_status=SummaryStatus.COMPLETED,
        )
        count1 = match_article(article)
        count2 = match_article(article)
        assert count1 == count2
        assert NewsArticleRelevance.objects.filter(article=article).count() == count1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_p17_news_matcher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement matcher**

```python
# projects/services/news/matcher.py
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
    ProjectStatus.NEW,
    ProjectStatus.SEARCHING,
    ProjectStatus.RECOMMENDING,
    ProjectStatus.INTERVIEWING,
    ProjectStatus.NEGOTIATING,
]


def match_article(article: NewsArticle) -> int:
    """Match a single article against active projects in the same org.

    Creates/updates NewsArticleRelevance rows for matches above threshold.
    Returns the number of matched projects.
    """
    org = article.source.organization

    projects = Project.objects.filter(
        organization=org,
        status__in=ACTIVE_STATUSES,
    ).select_related("client")

    matched = 0
    article_text = f"{article.title} {' '.join(article.tags)}".lower()

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

    logger.info(
        "Matched article '%s' to %d projects", article.title[:50], matched
    )
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
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_p17_news_matcher.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add projects/services/news/matcher.py tests/test_p17_news_matcher.py
git commit -m "feat(p17): add project relevance matcher service"
```

---

### Task 6: Management Command (fetch_news)

**Files:**
- Create: `projects/management/commands/fetch_news.py`
- Create: `tests/test_p17_news_command.py`

- [ ] **Step 1: Write command tests**

```python
# tests/test_p17_news_command.py
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
    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.summarizer._get_gemini_client")
    def test_full_pipeline(self, mock_gemini, mock_parse, source):
        # Setup RSS mock
        entry = MagicMock()
        entry.title = "Test Article"
        entry.link = "https://example.com/test-article"
        entry.get.return_value = ""
        entry.published_parsed = None
        mock_parse.return_value.entries = [entry]
        mock_parse.return_value.bozo = False

        # Setup Gemini mock
        mock_client = MagicMock()
        mock_gemini.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"summary": "요약입니다.", "tags": ["테스트"], "category": "hiring"}'
        mock_client.models.generate_content.return_value = mock_response

        out = StringIO()
        call_command("fetch_news", stdout=out)
        output = out.getvalue()

        assert "Fetching" in output or "Done" in output
        article = NewsArticle.objects.get(url="https://example.com/test-article")
        assert article.summary_status == SummaryStatus.COMPLETED

    @patch("projects.services.news.fetcher.feedparser.parse")
    def test_skips_inactive_sources(self, mock_parse, source):
        source.is_active = False
        source.save()

        out = StringIO()
        call_command("fetch_news", stdout=out)
        mock_parse.assert_not_called()

    @patch("projects.services.news.fetcher.feedparser.parse")
    @patch("projects.services.news.summarizer._get_gemini_client")
    def test_retries_failed_articles(self, mock_gemini, mock_parse, source):
        # Create a failed article
        article = NewsArticle.objects.create(
            source=source,
            title="Failed Article",
            url="https://example.com/failed",
            summary_status=SummaryStatus.FAILED,
        )
        mock_parse.return_value.entries = []
        mock_parse.return_value.bozo = False

        # Setup Gemini mock for retry
        mock_client = MagicMock()
        mock_gemini.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"summary": "재시도 성공.", "tags": ["테스트"], "category": "hr"}'
        mock_client.models.generate_content.return_value = mock_response

        call_command("fetch_news")
        article.refresh_from_db()
        assert article.summary_status == SummaryStatus.COMPLETED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_p17_news_command.py -v
```

Expected: ImportError or command not found.

- [ ] **Step 3: Create management command directory**

```bash
mkdir -p /home/work/synco/projects/management/commands
touch /home/work/synco/projects/management/__init__.py
touch /home/work/synco/projects/management/commands/__init__.py
```

Check if these files already exist first (they may from P15).

- [ ] **Step 4: Implement fetch_news command**

```python
# projects/management/commands/fetch_news.py
"""fetch_news — daily news pipeline: fetch → summarize → match → notify."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization, TelegramBinding
from projects.models import (
    NewsArticle,
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
        sources = NewsSource.objects.filter(
            is_active=True, type=NewsSourceType.RSS
        )
        total_created = 0
        total_skipped = 0

        for source in sources:
            try:
                created, skipped = fetch_articles(source)
                total_created += created
                total_skipped += skipped
            except Exception:
                logger.exception("Failed to fetch source: %s", source.name)

        self.stdout.write(
            f"  Fetch: {total_created} new, {total_skipped} existing"
        )

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

        self.stdout.write(
            f"  Summarize: {summarized} done, {failed} failed"
        )

        # Phase 3: Match summarized articles to projects
        # Only match articles summarized in this run (last 24h, completed)
        cutoff = timezone.now() - timedelta(hours=24)
        recent_articles = NewsArticle.objects.filter(
            summary_status=SummaryStatus.COMPLETED,
            updated_at__gte=cutoff,
        )
        total_matches = 0

        for article in recent_articles:
            total_matches += match_article(article)

        self.stdout.write(f"  Match: {total_matches} project-article links")

        # Phase 4: Telegram digest (per org)
        self._send_digests(cutoff)

        self.stdout.write(self.style.SUCCESS("Done."))

    def _send_digests(self, cutoff):
        """Send per-org news digests to Telegram-bound users."""
        today = timezone.now().date()

        for org in Organization.objects.all():
            # Get today's articles for this org
            org_articles = NewsArticle.objects.filter(
                source__organization=org,
                summary_status=SummaryStatus.COMPLETED,
                updated_at__gte=cutoff,
            ).order_by("-published_at")[:10]

            if not org_articles:
                continue

            # Build digest text
            digest_lines = ["[synco] 오늘의 뉴스 요약\n"]
            for article in org_articles:
                category_display = article.get_category_display() or "기타"
                digest_lines.append(
                    f"[{category_display}] {article.title}\n{article.url}\n"
                )
            digest_text = "\n".join(digest_lines)

            # Find recipients: active telegram bindings for this org
            bindings = TelegramBinding.objects.filter(
                user__membership__organization=org,
                is_active=True,
            ).select_related("user")

            sent = 0
            for binding in bindings:
                # Dedupe: skip if already sent today
                already_sent = Notification.objects.filter(
                    recipient=binding.user,
                    type=Notification.Type.NEWS,
                    created_at__date=today,
                ).exists()

                if already_sent:
                    continue

                with transaction.atomic():
                    notif = Notification.objects.create(
                        recipient=binding.user,
                        type=Notification.Type.NEWS,
                        title="오늘의 뉴스 요약",
                        body=digest_text,
                    )

                transaction.on_commit(
                    lambda n=notif, t=digest_text: send_notification(n, text=t)
                )
                sent += 1

            if sent:
                self.stdout.write(f"  Telegram: {sent} digests for {org.name}")
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_p17_news_command.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add projects/management/ tests/test_p17_news_command.py
git commit -m "feat(p17): add fetch_news management command"
```

---

### Task 7: URL Routing + Views + Forms

**Files:**
- Create: `projects/urls_news.py`
- Modify: `main/urls.py`
- Create: `projects/views_news.py`
- Modify: `projects/forms.py`
- Create: `tests/test_p17_news_views.py`

- [ ] **Step 1: Write view tests**

```python
# tests/test_p17_news_views.py
"""P17: News feed view tests."""

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    Project,
    SummaryStatus,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def auth_client(user):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def source(org):
    return NewsSource.objects.create(
        organization=org,
        name="Test Feed",
        url="https://example.com/feed",
        type=NewsSourceType.RSS,
        category=NewsCategory.HIRING,
    )


@pytest.fixture
def article(source):
    return NewsArticle.objects.create(
        source=source,
        title="Test News",
        url="https://example.com/news-1",
        summary="Summary text",
        category=NewsCategory.HIRING,
        summary_status=SummaryStatus.COMPLETED,
        published_at=timezone.now(),
    )


class TestNewsFeed:
    def test_feed_requires_login(self, db):
        c = TestClient()
        resp = c.get("/news/")
        assert resp.status_code == 302
        assert "/accounts/login" in resp.url or "/login" in resp.url

    def test_feed_page_loads(self, auth_client, article):
        resp = auth_client.get("/news/")
        assert resp.status_code == 200
        assert "Test News" in resp.content.decode()

    def test_feed_updates_last_seen(self, auth_client, user, article):
        assert user.last_news_seen_at is None
        auth_client.get("/news/")
        user.refresh_from_db()
        assert user.last_news_seen_at is not None


class TestNewsFilter:
    def test_filter_by_category(self, auth_client, source):
        NewsArticle.objects.create(
            source=source, title="Hiring News", url="https://example.com/h",
            category=NewsCategory.HIRING, summary_status=SummaryStatus.COMPLETED,
            published_at=timezone.now(),
        )
        NewsArticle.objects.create(
            source=source, title="HR News", url="https://example.com/hr",
            category=NewsCategory.HR, summary_status=SummaryStatus.COMPLETED,
            published_at=timezone.now(),
        )
        resp = auth_client.get("/news/filter/?category=hiring")
        content = resp.content.decode()
        assert "Hiring News" in content
        assert "HR News" not in content


class TestNewsSourceCRUD:
    def test_source_list(self, auth_client, source):
        resp = auth_client.get("/news/sources/")
        assert resp.status_code == 200
        assert "Test Feed" in resp.content.decode()

    def test_source_create(self, auth_client, org):
        resp = auth_client.post("/news/sources/new/", {
            "name": "New Source",
            "url": "https://newssite.com/feed",
            "type": NewsSourceType.RSS,
            "category": NewsCategory.INDUSTRY,
        })
        assert resp.status_code == 302
        assert NewsSource.objects.filter(name="New Source").exists()

    def test_source_toggle(self, auth_client, source):
        assert source.is_active is True
        resp = auth_client.post(f"/news/sources/{source.pk}/toggle/")
        assert resp.status_code == 302
        source.refresh_from_db()
        assert source.is_active is False

    def test_source_delete(self, auth_client, source):
        resp = auth_client.post(f"/news/sources/{source.pk}/delete/")
        assert resp.status_code == 302
        assert not NewsSource.objects.filter(pk=source.pk).exists()

    def test_non_staff_blocked_from_source_crud(self, db, org):
        viewer = User.objects.create_user(username="viewer", password="test1234")
        Membership.objects.create(user=viewer, organization=org, role="viewer")
        c = TestClient()
        c.login(username="viewer", password="test1234")
        resp = c.get("/news/sources/")
        assert resp.status_code in (302, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_p17_news_views.py -v
```

Expected: ImportError or 404 errors.

- [ ] **Step 3: Create NewsSourceForm in projects/forms.py**

Append to `projects/forms.py`:

```python
from .models import NewsSource

class NewsSourceForm(forms.ModelForm):
    class Meta:
        model = NewsSource
        fields = ["name", "url", "type", "category"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CSS, "placeholder": "소스 이름"}),
            "url": forms.URLInput(attrs={"class": INPUT_CSS, "placeholder": "https://example.com/feed.xml"}),
            "type": forms.Select(attrs={"class": INPUT_CSS}),
            "category": forms.Select(attrs={"class": INPUT_CSS}),
        }
        labels = {
            "name": "소스 이름",
            "url": "피드 URL",
            "type": "유형",
            "category": "카테고리",
        }

    def clean_url(self):
        url = self.cleaned_data.get("url", "")
        if url and not url.startswith(("http://", "https://")):
            raise forms.ValidationError("http:// 또는 https:// URL만 허용됩니다.")
        return url
```

- [ ] **Step 4: Create views_news.py**

```python
# projects/views_news.py
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
```

- [ ] **Step 5: Create urls_news.py**

```python
# projects/urls_news.py
from django.urls import path

from . import views_news

app_name = "news"

urlpatterns = [
    path("", views_news.news_feed, name="news_feed"),
    path("filter/", views_news.news_filter, name="news_filter"),
    path("sources/", views_news.news_sources, name="news_sources"),
    path("sources/new/", views_news.news_source_create, name="news_source_create"),
    path("sources/<uuid:pk>/edit/", views_news.news_source_update, name="news_source_update"),
    path("sources/<uuid:pk>/delete/", views_news.news_source_delete, name="news_source_delete"),
    path("sources/<uuid:pk>/toggle/", views_news.news_source_toggle, name="news_source_toggle"),
]
```

- [ ] **Step 6: Register in main/urls.py**

Add to `main/urls.py` urlpatterns (before the closing `]`):

```python
    path("news/", include("projects.urls_news")),
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_p17_news_views.py -v
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add projects/urls_news.py projects/views_news.py projects/forms.py main/urls.py tests/test_p17_news_views.py
git commit -m "feat(p17): add news feed views, URLs, and source CRUD"
```

---

### Task 8: Templates + Sidebar

**Files:**
- Create: `projects/templates/projects/news_feed.html`
- Create: `projects/templates/projects/partials/news_list.html`
- Create: `projects/templates/projects/news_sources.html`
- Create: `projects/templates/projects/news_source_form.html`
- Modify: `templates/common/nav_sidebar.html`
- Modify: `projects/context_processors.py`
- Modify: `main/settings.py` (context processor registration if needed)

- [ ] **Step 1: Create news_feed.html**

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}뉴스피드 — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">

  <div class="flex items-center justify-between">
    <h1 class="text-heading font-bold">뉴스피드</h1>
    {% if is_staff %}
    <a href="{% url 'news:news_sources' %}"
       hx-get="{% url 'news:news_sources' %}" hx-target="#main-content" hx-push-url="true"
       class="text-[15px] text-primary hover:text-primary-dark transition">
      소스 관리
    </a>
    {% endif %}
  </div>

  <!-- Category filter tabs -->
  <div class="flex gap-2 overflow-x-auto pb-1">
    <button hx-get="{% url 'news:news_filter' %}" hx-target="#news-list" hx-swap="innerHTML"
            class="px-3 py-1.5 rounded-full text-[14px] font-medium whitespace-nowrap
            {% if not active_category %}bg-primary text-white{% else %}bg-gray-100 text-gray-600 hover:bg-gray-200{% endif %}">
      전체
    </button>
    {% for value, label in categories %}
    <button hx-get="{% url 'news:news_filter' %}?category={{ value }}" hx-target="#news-list" hx-swap="innerHTML"
            class="px-3 py-1.5 rounded-full text-[14px] font-medium whitespace-nowrap
            {% if active_category == value %}bg-primary text-white{% else %}bg-gray-100 text-gray-600 hover:bg-gray-200{% endif %}">
      {{ label }}
    </button>
    {% endfor %}
  </div>

  <!-- Related news section -->
  {% if related_articles %}
  <div class="space-y-3">
    <h2 class="text-[16px] font-semibold text-gray-700">내 프로젝트 관련 뉴스</h2>
    {% for article in related_articles %}
    <a href="{{ article.url }}" target="_blank" rel="noopener"
       class="block bg-blue-50 border border-blue-100 rounded-lg p-4 hover:bg-blue-100 transition">
      <div class="flex items-start gap-2">
        <span class="text-[12px] font-medium text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full whitespace-nowrap">
          {{ article.get_category_display|default:"기타" }}
        </span>
        <h3 class="text-[15px] font-medium text-gray-900 line-clamp-2">{{ article.title }}</h3>
      </div>
      {% if article.summary %}
      <p class="text-[14px] text-gray-600 mt-1 line-clamp-2">{{ article.summary }}</p>
      {% endif %}
      <div class="flex items-center gap-2 mt-2 text-[12px] text-gray-400">
        <span>{{ article.source.name }}</span>
        {% if article.published_at %}
        <span>{{ article.published_at|date:"m/d H:i" }}</span>
        {% endif %}
      </div>
    </a>
    {% endfor %}
  </div>
  {% endif %}

  <!-- All news section -->
  <div class="space-y-3">
    <h2 class="text-[16px] font-semibold text-gray-700">최신 뉴스</h2>
    <div id="news-list">
      {% include "projects/partials/news_list.html" with articles=all_articles %}
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Create partials/news_list.html**

```html
{% for article in articles %}
<a href="{{ article.url }}" target="_blank" rel="noopener"
   class="block bg-white border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition mb-3">
  <div class="flex items-start gap-2">
    <span class="text-[12px] font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full whitespace-nowrap">
      {{ article.get_category_display|default:"기타" }}
    </span>
    <h3 class="text-[15px] font-medium text-gray-900 line-clamp-2">{{ article.title }}</h3>
  </div>
  {% if article.summary %}
  <p class="text-[14px] text-gray-600 mt-1 line-clamp-2">{{ article.summary }}</p>
  {% endif %}
  <div class="flex items-center gap-3 mt-2 text-[12px] text-gray-400">
    <span>{{ article.source.name }}</span>
    {% if article.published_at %}
    <span>{{ article.published_at|date:"m/d H:i" }}</span>
    {% endif %}
    {% if article.tags %}
    <div class="flex gap-1">
      {% for tag in article.tags|slice:":3" %}
      <span class="text-gray-400">#{{ tag }}</span>
      {% endfor %}
    </div>
    {% endif %}
  </div>
</a>
{% empty %}
<div class="bg-gray-50 rounded-lg p-8 text-center text-gray-500 text-[15px]">
  뉴스가 없습니다.
</div>
{% endfor %}
```

- [ ] **Step 3: Create news_sources.html**

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}뉴스 소스 관리 — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">

  <div class="flex items-center justify-between">
    <h1 class="text-heading font-bold">뉴스 소스 관리</h1>
    <a href="{% url 'news:news_source_create' %}"
       hx-get="{% url 'news:news_source_create' %}" hx-target="#main-content" hx-push-url="true"
       class="bg-primary text-white px-4 py-2 rounded-lg text-[15px] font-medium hover:bg-primary-dark transition">
      소스 추가
    </a>
  </div>

  {% if sources %}
  <div class="space-y-3">
    {% for source in sources %}
    <div class="bg-white border border-gray-200 rounded-lg p-4">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-[15px] font-medium text-gray-900">{{ source.name }}</h3>
          <p class="text-[13px] text-gray-500 mt-0.5">{{ source.url }}</p>
          <div class="flex items-center gap-2 mt-1 text-[12px]">
            <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{{ source.get_type_display }}</span>
            <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{{ source.get_category_display }}</span>
            {% if source.is_active %}
            <span class="px-2 py-0.5 rounded-full bg-green-100 text-green-600">활성</span>
            {% else %}
            <span class="px-2 py-0.5 rounded-full bg-red-100 text-red-600">비활성</span>
            {% endif %}
            {% if source.last_fetched_at %}
            <span class="text-gray-400">최근 수집: {{ source.last_fetched_at|date:"m/d H:i" }}</span>
            {% endif %}
          </div>
        </div>
        <div class="flex items-center gap-2">
          <form method="post" action="{% url 'news:news_source_toggle' source.pk %}">
            {% csrf_token %}
            <button type="submit" class="text-[13px] text-gray-500 hover:text-gray-700 px-2 py-1">
              {% if source.is_active %}비활성화{% else %}활성화{% endif %}
            </button>
          </form>
          <a href="{% url 'news:news_source_update' source.pk %}"
             hx-get="{% url 'news:news_source_update' source.pk %}" hx-target="#main-content" hx-push-url="true"
             class="text-[13px] text-primary hover:text-primary-dark px-2 py-1">수정</a>
          <form method="post" action="{% url 'news:news_source_delete' source.pk %}"
                onsubmit="return confirm('정말 삭제하시겠습니까?')">
            {% csrf_token %}
            <button type="submit" class="text-[13px] text-red-500 hover:text-red-700 px-2 py-1">삭제</button>
          </form>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="bg-gray-50 rounded-lg p-8 text-center text-gray-500 text-[15px]">
    등록된 소스가 없습니다.
  </div>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 4: Create news_source_form.html**

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}
{% load widget_tweaks %}

{% block title %}{% if is_edit %}소스 수정{% else %}소스 추가{% endif %} — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6 max-w-lg">

  <h1 class="text-heading font-bold">{% if is_edit %}소스 수정{% else %}소스 추가{% endif %}</h1>

  <form method="post" class="space-y-4">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-[14px] font-medium text-gray-700 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}
      <p class="text-[13px] text-red-500 mt-1">{{ field.errors.0 }}</p>
      {% endif %}
    </div>
    {% endfor %}

    <div class="flex gap-3 pt-2">
      <button type="submit"
              class="bg-primary text-white px-6 py-2.5 rounded-lg text-[15px] font-medium hover:bg-primary-dark transition">
        {% if is_edit %}수정{% else %}추가{% endif %}
      </button>
      <a href="{% url 'news:news_sources' %}"
         hx-get="{% url 'news:news_sources' %}" hx-target="#main-content" hx-push-url="true"
         class="px-6 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100 transition">
        취소
      </a>
    </div>
  </form>

</div>
{% endblock %}
```

- [ ] **Step 5: Update nav_sidebar.html — add news menu item**

Add before the settings `<a>` tag in `templates/common/nav_sidebar.html`:

```html
  <a href="/news/"
     hx-get="/news/" hx-target="#main-content" hx-push-url="true"
     data-nav="news"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"/></svg>
    뉴스피드
    {% if has_new_news %}<span class="w-2 h-2 bg-red-500 rounded-full"></span>{% endif %}
  </a>
```

Also add `'news'` to the `updateSidebar` JavaScript function's matching logic:

```javascript
(key === 'news' && path.startsWith('/news')) ||
```

- [ ] **Step 6: Update context_processors.py — add news dot indicator**

Add a new context processor function in `projects/context_processors.py`:

```python
def has_new_news(request):
    """Inject has_new_news flag for sidebar dot indicator."""
    if not request.user.is_authenticated:
        return {}

    try:
        membership = request.user.membership
    except Exception:
        return {}

    from projects.models import NewsArticle, SummaryStatus

    last_seen = request.user.last_news_seen_at
    if last_seen is None:
        # Never visited — check if any news exists
        has_new = NewsArticle.objects.filter(
            source__organization=membership.organization,
            summary_status=SummaryStatus.COMPLETED,
        ).exists()
    else:
        has_new = NewsArticle.objects.filter(
            source__organization=membership.organization,
            summary_status=SummaryStatus.COMPLETED,
            published_at__gt=last_seen,
        ).exists()

    return {"has_new_news": has_new}
```

Register in `main/settings.py` if not already there — add `"projects.context_processors.has_new_news"` to the context_processors list.

- [ ] **Step 7: Also pass is_staff to news_feed view context**

In `projects/views_news.py`, update the `news_feed` view's render context to include `"is_staff": _is_staff(request)`.

- [ ] **Step 8: Run all tests**

```bash
uv run pytest tests/test_p17_news_views.py -v
```

Expected: All tests pass.

- [ ] **Step 9: Run lint**

```bash
uv run ruff check projects/views_news.py projects/urls_news.py projects/forms.py projects/context_processors.py
uv run ruff format projects/views_news.py projects/urls_news.py projects/forms.py projects/context_processors.py
```

- [ ] **Step 10: Commit**

```bash
git add projects/views_news.py projects/urls_news.py projects/forms.py main/urls.py \
  projects/templates/projects/news_feed.html projects/templates/projects/partials/news_list.html \
  projects/templates/projects/news_sources.html projects/templates/projects/news_source_form.html \
  templates/common/nav_sidebar.html projects/context_processors.py main/settings.py \
  tests/test_p17_news_views.py
git commit -m "feat(p17): add news feed UI, source CRUD, sidebar integration"
```

---

### Task 9: Final Integration + Full Test Suite

**Files:**
- All test files

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests pass, including existing tests (no regressions).

- [ ] **Step 2: Run lint on all new files**

```bash
uv run ruff check .
uv run ruff format .
```

- [ ] **Step 3: Check migrations**

```bash
uv run python manage.py makemigrations --check --dry-run
```

Expected: "No changes detected".

- [ ] **Step 4: Final commit (if any lint fixes)**

```bash
git add -A
git commit -m "style(p17): apply ruff lint fixes and formatting"
```

<!-- forge:p17-news-feed:구현담금질:complete:2026-04-10T13:07:47+09:00 -->
