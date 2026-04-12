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
        assert Submission.objects.filter(project=project, candidate=candidate).exists()

    @pytest.mark.django_db
    def test_invalid_form_still_returns_form(self, auth_client, project):
        """폼 유효성 실패 시 기존 동작 유지 — HX-Retarget 없이 폼 재렌더링."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {},  # 빈 데이터 → validation error
        )
        # 유효성 실패 시 폼을 다시 렌더링 (200 with form HTML, no HX-Retarget)
        assert resp.status_code == 200
        assert "HX-Retarget" not in resp.headers
        assert "HX-Reswap" not in resp.headers


# --- contact_update interest banner tests ---


class TestContactInterestBanner:
    """contact_update에서 결과를 '관심'으로 변경하면
    응답에 추천 유도 배너가 포함되어야 한다."""

    @pytest.mark.django_db
    def test_interest_result_shows_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """결과가 '관심'으로 변경되면 배너가 포함된다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "추천 서류 작성하기" in content

    @pytest.mark.django_db
    def test_interest_result_has_htmx_headers(
        self, auth_client, project, candidate, user_with_org
    ):
        """'관심' 전환 시 HX-Retarget, HX-Reswap, HX-Trigger 헤더가 올바르다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        assert resp.headers.get("HX-Retarget") == "#tab-content"
        assert resp.headers.get("HX-Reswap") == "innerHTML"
        assert "contactChanged" in resp.headers.get("HX-Trigger", "")

    @pytest.mark.django_db
    def test_non_interest_result_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """결과가 '관심'이 아니면 배너가 포함되지 않는다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "미응답",
                "notes": "",
            },
        )
        # 204 반환 (기존 동작) — 배너 없음
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_interest_but_already_submitted_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """이미 Submission이 있으면 배너를 표시하지 않는다."""
        Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        # 이미 제출 완료이므로 배너 없이 204 반환
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_already_interested_edit_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """이미 '관심'인 컨택의 메모만 수정하면 배너가 표시되지 않는다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",  # 이미 관심
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",  # 변경 없음
                "notes": "메모 추가",
            },
        )
        # 관심→관심 (변경 없음)이므로 배너 없이 204 반환
        assert resp.status_code == 204
