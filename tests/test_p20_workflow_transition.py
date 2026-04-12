"""P20: Workflow transition tests.

Tests for submission_create auto-transition to submissions tab.
"""

import json

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project, Submission


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(
        name="Acme Corp",
        industry="IT",
        organization=org,
    )


@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        title="Backend Dev",
        client=client_obj,
        organization=org,
        status="searching",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(
        name="홍길동",
        owned_by=org,
    )


@pytest.fixture
def interested_contact(project, candidate, user_with_org):
    """컨택 결과 '관심'인 Contact — SubmissionForm이 후보자를 선택 가능하게 함."""
    return Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        channel=Contact.Channel.PHONE,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED,
    )


# --- submission_create auto-transition tests ---


class TestSubmissionCreateAutoTransition:
    """submission_create 성공 시 추천 탭 파셜을 반환하고
    HX-Retarget + tabChanged 헤더가 포함되어야 한다."""

    @pytest.mark.django_db
    def test_submission_create_returns_submissions_tab(
        self, auth_client, project, candidate, interested_contact
    ):
        """POST 성공 시 204 대신 200 + 추천 탭 HTML 반환."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert resp.status_code == 200
        assert "추천 이력" in resp.content.decode()

    @pytest.mark.django_db
    def test_submission_create_has_retarget_header(
        self, auth_client, project, candidate, interested_contact
    ):
        """HX-Retarget 헤더가 #tab-content를 가리켜야 한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert resp.headers.get("HX-Retarget") == "#tab-content"
        assert resp.headers.get("HX-Reswap") == "innerHTML"

    @pytest.mark.django_db
    def test_submission_create_has_structured_tab_changed_trigger(
        self, auth_client, project, candidate, interested_contact
    ):
        """HX-Trigger에 구조화된 tabChanged + submissionChanged가 포함되어야 한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        hx_trigger = resp.headers.get("HX-Trigger", "{}")
        payload = json.loads(hx_trigger)
        assert payload["tabChanged"] == {"activeTab": "submissions"}
        assert "submissionChanged" in payload

    @pytest.mark.django_db
    def test_submission_actually_created(
        self, auth_client, project, candidate, interested_contact
    ):
        """Submission 레코드가 실제로 생성되어야 한다."""
        auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert Submission.objects.filter(
            project=project, candidate=candidate
        ).exists()

    @pytest.mark.django_db
    def test_invalid_form_still_returns_form(
        self, auth_client, project
    ):
        """폼 유효성 실패 시 기존 동작 유지 — HX-Retarget 없이 폼 재렌더링."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {},  # 빈 데이터 → validation error
        )
        # 유효성 실패 시 폼을 다시 렌더링 (200 with form HTML, no HX-Retarget)
        assert resp.status_code == 200
        assert "HX-Retarget" not in resp.headers
        assert "HX-Reswap" not in resp.headers
