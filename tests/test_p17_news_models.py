"""P17: News feed model tests."""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import User
from projects.models import (
    NewsArticle,
    NewsArticleRelevance,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    Project,
    SummaryStatus)
from clients.models import Client



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="tester", password="test1234")
    return u


@pytest.fixture
def client_co(db):
    return Client.objects.create(name="Acme Corp")


@pytest.fixture
def project(client_co, user):
    return Project.objects.create(client=client_co, title="Backend Dev", created_by=user)


@pytest.fixture
def news_source(db):
    return NewsSource.objects.create(
        name="TechCrunch Korea",
        url="https://techcrunch.com/feed/",
        type=NewsSourceType.RSS,
        category=NewsCategory.INDUSTRY)


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
        tags=["AI", "채용"])


class TestNewsSource:
    def test_create_source(self, news_source):
        assert news_source.is_active is True
        assert news_source.type == NewsSourceType.RSS
        assert news_source.last_fetched_at is None
        assert news_source.id is not None  # UUID PK from BaseModel

    def test_source_str(self, news_source):
        assert str(news_source) == "TechCrunch Korea"

    @pytest.mark.django_db
    def test_source_ordering(self):
        NewsSource.objects.create(
            name="A",
            url="https://a.com/feed",
            category=NewsCategory.HR)
        s2 = NewsSource.objects.create(
            name="B",
            url="https://b.com/feed",
            category=NewsCategory.HR)
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

    def test_set_null_on_source_delete(self, news_article, news_source):
        """I-R1-02: Source deletion must NOT cascade-delete articles."""
        article_id = news_article.id
        news_source.delete()
        article = NewsArticle.objects.get(id=article_id)
        assert article.source is None


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
