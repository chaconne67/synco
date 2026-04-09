"""P14: Voice endpoint integration tests."""

import io
import json
from unittest.mock import patch

import pytest
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="view_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def auth_client(user):
    c = TestClient()
    c.login(username="view_tester", password="test1234")
    return c


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="View Client", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="View Test",
        created_by=user,
    )


@pytest.fixture
def candidate(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


def test_transcribe_endpoint_requires_auth(db):
    c = TestClient()
    resp = c.post("/voice/transcribe/")
    assert resp.status_code in (302, 403)


@patch("projects.views_voice.transcribe")
def test_transcribe_endpoint(mock_transcribe, auth_client):
    mock_transcribe.return_value = "홍길동 전화했어"
    audio = io.BytesIO(b"fake audio")
    audio.name = "voice.webm"
    resp = auth_client.post(
        "/voice/transcribe/",
        {"audio": audio, "mode": "command"},
        format="multipart",
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["text"] == "홍길동 전화했어"


def test_context_endpoint(auth_client, project):
    resp = auth_client.get(
        "/voice/context/",
        {"page": "project_detail", "project_id": str(project.pk)},
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["project_id"] == str(project.pk)


def test_history_endpoint(auth_client):
    resp = auth_client.get("/voice/history/")
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert "turns" in data


def test_reset_endpoint(auth_client):
    resp = auth_client.post("/voice/reset/")
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["ok"] is True


def test_meeting_upload_requires_auth(db):
    c = TestClient()
    resp = c.post("/voice/meeting-upload/")
    assert resp.status_code in (302, 403)


def test_meeting_status_not_found(auth_client):
    resp = auth_client.get(
        "/voice/meeting-status/00000000-0000-0000-0000-000000000000/"
    )
    assert resp.status_code == 404
