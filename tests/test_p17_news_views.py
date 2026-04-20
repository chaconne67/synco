"""P17: News feed view tests."""

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import User
from projects.models import (
    NewsArticle,
    NewsCategory,
    NewsSource,
    NewsSourceType,
    SummaryStatus)



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="tester", password="test1234")
    return u


@pytest.fixture
def auth_client(user):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def source(org):
    return NewsSource.objects.create(
        name="Test Feed",
        url="https://example.com/feed",
        type=NewsSourceType.RSS,
        category=NewsCategory.HIRING)


@pytest.fixture
def article(source):
    return NewsArticle.objects.create(
        source=source,
        title="Test News",
        url="https://example.com/news-1",
        summary="Summary text",
        category=NewsCategory.HIRING,
        summary_status=SummaryStatus.COMPLETED,
        published_at=timezone.now())


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
            source=source,
            title="Hiring News",
            url="https://example.com/h",
            category=NewsCategory.HIRING,
            summary_status=SummaryStatus.COMPLETED,
            published_at=timezone.now())
        NewsArticle.objects.create(
            source=source,
            title="HR News",
            url="https://example.com/hr",
            category=NewsCategory.HR,
            summary_status=SummaryStatus.COMPLETED,
            published_at=timezone.now())
        resp = auth_client.get("/news/filter/?category=hiring")
        content = resp.content.decode()
        assert "Hiring News" in content
        assert "HR News" not in content


class TestNewsSourceCRUD:
    def test_source_list(self, auth_client, source):
        resp = auth_client.get("/news/sources/")
        assert resp.status_code == 200
        assert "Test Feed" in resp.content.decode()

    def test_source_create(self, auth_client):
        resp = auth_client.post(
            "/news/sources/new/",
            {
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

    def test_non_staff_blocked_from_source_crud(self, db):
        viewer = User.objects.create_user(username="viewer", password="test1234")
            c = TestClient()
        c.login(username="viewer", password="test1234")
        resp = c.get("/news/sources/")
        assert resp.status_code == 403
