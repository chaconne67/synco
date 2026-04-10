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
