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


# Amendment A12: /voice/intent/ endpoint
@patch("projects.views_voice.parse_intent")
def test_intent_endpoint(mock_parse, auth_client, project, candidate):
    from projects.services.voice.intent_parser import IntentResult

    mock_parse.return_value = IntentResult(
        intent="status_query",
        entities={},
        confidence=0.9,
        missing_fields=[],
    )
    resp = auth_client.post(
        "/voice/intent/",
        json.dumps(
            {
                "text": "현황 알려줘",
                "context": json.dumps(
                    {"page": "project_detail", "project_id": str(project.pk)}
                ),
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["intent"] == "status_query"


# Amendment A12: /voice/preview/ endpoint
def test_preview_endpoint(auth_client, project):
    resp = auth_client.post(
        "/voice/preview/",
        json.dumps(
            {
                "intent": "status_query",
                "entities": {},
                "project_id": str(project.pk),
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["ok"] is True
    assert "preview_token" in data


# Amendment A12: /voice/confirm/ with valid and reused tokens
def test_confirm_valid_and_reused_token(auth_client, project):
    # Get a preview token first
    resp1 = auth_client.post(
        "/voice/preview/",
        json.dumps(
            {
                "intent": "status_query",
                "entities": {},
                "project_id": str(project.pk),
            }
        ),
        content_type="application/json",
    )
    data1 = json.loads(resp1.content)
    token = data1["preview_token"]

    # Confirm with valid token
    resp2 = auth_client.post(
        "/voice/confirm/",
        json.dumps(
            {
                "intent": "status_query",
                "entities": {},
                "project_id": str(project.pk),
                "preview_token": token,
            }
        ),
        content_type="application/json",
    )
    assert resp2.status_code == 200
    data2 = json.loads(resp2.content)
    assert data2["ok"] is True

    # Reuse the same token -> 409
    resp3 = auth_client.post(
        "/voice/confirm/",
        json.dumps(
            {
                "intent": "status_query",
                "entities": {},
                "project_id": str(project.pk),
                "preview_token": token,
            }
        ),
        content_type="application/json",
    )
    assert resp3.status_code == 409


# Amendment A12: multi-turn flow (pending intent -> follow-up)
@patch("projects.views_voice.parse_intent")
def test_multi_turn_flow(mock_parse, auth_client, project, candidate):
    from projects.services.voice.intent_parser import IntentResult

    # First turn: contact_record with missing fields
    mock_parse.return_value = IntentResult(
        intent="contact_record",
        entities={"candidate_name": "홍길동", "channel": "전화"},
        confidence=0.9,
        missing_fields=["contacted_at", "result"],
    )
    resp1 = auth_client.post(
        "/voice/intent/",
        json.dumps(
            {
                "text": "홍길동 전화했어",
                "context": json.dumps(
                    {"page": "project_detail", "project_id": str(project.pk)}
                ),
            }
        ),
        content_type="application/json",
    )
    assert resp1.status_code == 200
    data1 = json.loads(resp1.content)
    assert data1["intent"] == "contact_record"
    assert len(data1["missing_fields"]) > 0

    # Second turn: follow-up providing missing info
    mock_parse.return_value = IntentResult(
        intent="contact_record",
        entities={"result": "관심"},
        confidence=0.9,
        missing_fields=[],
    )
    resp2 = auth_client.post(
        "/voice/intent/",
        json.dumps(
            {
                "text": "관심 있대",
                "context": json.dumps(
                    {"page": "project_detail", "project_id": str(project.pk)}
                ),
            }
        ),
        content_type="application/json",
    )
    assert resp2.status_code == 200
    data2 = json.loads(resp2.content)
    assert data2["intent"] == "contact_record"
    # "result" should now be in collected entities
    assert data2["entities"].get("result") == "관심"
