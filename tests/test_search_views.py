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
def test_login_required(client):
    resp = client.get("/candidates/")
    assert resp.status_code == 302
