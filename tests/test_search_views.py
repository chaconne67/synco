import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from candidates.models import Candidate, Category

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="test1234")


@pytest.fixture
def auth_client(user):
    client = Client()
    client.login(username="tester", password="test1234")
    return client


@pytest.fixture
def category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def candidate(db, category):
    c = Candidate.objects.create(
        name="강솔찬",
        current_company="현대엠시트",
        total_experience_years=12,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.mark.django_db
def test_candidate_list_page(auth_client, candidate):
    resp = auth_client.get("/candidates/")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_list_filter_category(auth_client, candidate, category):
    resp = auth_client.get(f"/candidates/?category={category.name}")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_detail_page(auth_client, candidate):
    resp = auth_client.get(f"/candidates/{candidate.pk}/")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
@patch("candidates.views.parse_search_query")
@patch("candidates.views.hybrid_search")
def test_search_chat(mock_search, mock_parse, auth_client, candidate):
    mock_parse.return_value = {
        "filters": {"category": "Accounting"},
        "semantic_query": "회계",
        "action": "new",
        "ai_message": "회계 후보자 1명을 찾았습니다.",
    }
    mock_search.return_value = [candidate]

    resp = auth_client.post(
        "/candidates/search/",
        data=json.dumps({"message": "회계 찾아줘"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["ai_message"] == "회계 후보자 1명을 찾았습니다."
    assert data["result_count"] == 1


@pytest.mark.django_db
def test_login_required(client):
    resp = client.get("/candidates/")
    assert resp.status_code == 302
