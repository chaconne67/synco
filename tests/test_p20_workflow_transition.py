"""P20: Workflow transition tests.

Tests for submission_create auto-transition to submissions tab,
and funnel navigation (t23).
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


# --- Funnel navigation tests (t23) ---


class TestFunnelNavigation:
    """개요 탭 퍼널의 각 단계가 클릭 가능한 링크로 렌더링되어야 한다."""

    @pytest.mark.django_db
    def test_overview_funnel_has_clickable_links(
        self, auth_client, project
    ):
        """퍼널 항목에 hx-get 링크가 포함되어야 한다."""
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # 4개 탭 URL이 있어야 함
        assert f"/projects/{project.pk}/tab/contacts/" in content
        assert f"/projects/{project.pk}/tab/submissions/" in content
        assert f"/projects/{project.pk}/tab/interviews/" in content
        assert f"/projects/{project.pk}/tab/offers/" in content
        # 관심 필터 링크
        assert f"/projects/{project.pk}/tab/contacts/?result=" in content
        # hx-get 속성이 퍼널 영역에 존재
        assert 'hx-target="#tab-content"' in content
        # tabChanged 이벤트 발행 코드 존재
        assert "tabChanged" in content

    @pytest.mark.django_db
    def test_overview_funnel_includes_interested_count(
        self, auth_client, project, candidate, user_with_org
    ):
        """퍼널에 '관심' 카운트가 정확히 포함되어야 한다."""
        # 관심 컨택 1건
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.INTERESTED,
        )
        # 미응답 컨택 1건 (관심 아님)
        other_candidate = Candidate.objects.create(
            name="김철수",
            owned_by=project.organization,
        )
        Contact.objects.create(
            project=project,
            candidate=other_candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.NO_RESPONSE,
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        normalized = content.replace("\n", "").replace("  ", "")
        # 관심 카운트는 1이어야 함 (미응답 제외)
        assert '>관심 <span class="font-semibold text-gray-800">1</span>' in normalized
        # 컨택 카운트는 2이어야 함 (RESERVED 제외, 나머지 모두)
        assert '>컨택 <span class="font-semibold text-gray-800">2</span>' in normalized

    @pytest.mark.django_db
    def test_overview_funnel_excludes_reserved_from_contacts(
        self, auth_client, project, candidate, user_with_org
    ):
        """퍼널 컨택 카운트에서 예정(RESERVED)이 제외되어야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timezone.timedelta(hours=1),
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # RESERVED만 있으므로 퍼널 컨택 카운트는 0이어야 함
        assert '>컨택 <span class="font-semibold text-gray-800">0</span>' in content.replace("\n", "").replace("  ", "")

    @pytest.mark.django_db
    def test_contacts_tab_result_filter(
        self, auth_client, project, candidate, user_with_org
    ):
        """컨택 탭에 ?result=관심 필터가 동작해야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.INTERESTED,
        )
        other_candidate = Candidate.objects.create(
            name="김철수",
            owned_by=project.organization,
        )
        Contact.objects.create(
            project=project,
            candidate=other_candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.NO_RESPONSE,
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/?result=관심",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        assert "홍길동" in content  # 관심 결과 후보자
        assert "김철수" not in content  # 미응답 결과 후보자는 필터됨


# --- Tab badge new indicator tests (t24) ---


class TestTabBadgeNewIndicator:
    """탭 뱃지 data 속성 렌더링 검증 (마크업 회귀 테스트)."""

    @pytest.mark.django_db
    def test_all_tabs_have_data_tab_attributes(
        self, auth_client, project
    ):
        """탭바의 모든 6개 버튼에 data-tab 속성이 있어야 한다."""
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()
        for tab_name in ["overview", "search", "contacts", "submissions", "interviews", "offers"]:
            assert f'data-tab="{tab_name}"' in content, f'data-tab="{tab_name}" not found'

    @pytest.mark.django_db
    def test_badge_present_with_data_attrs_when_count_positive(
        self, auth_client, project, candidate, user_with_org
    ):
        """컨택이 있으면 contacts 탭 뱃지에 data-badge-count와 data-latest가 렌더링된다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()

        # contacts 탭 버튼 블록 내에 data-badge-count와 data-latest가 존재해야 한다
        contacts_start = content.find('data-tab="contacts"')
        assert contacts_start != -1, "contacts tab button not found"
        # 다음 탭 버튼까지의 범위로 한정
        contacts_end = content.find('data-tab="submissions"', contacts_start)
        contacts_block = content[contacts_start:contacts_end]
        assert "data-badge-count" in contacts_block, "data-badge-count not in contacts tab"
        assert "data-latest" in contacts_block, "data-latest not in contacts tab"

    @pytest.mark.django_db
    def test_badge_absent_when_count_zero(
        self, auth_client, project
    ):
        """컨택이 없으면 contacts 탭 뱃지 span이 렌더링되지 않아야 한다."""
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()

        # contacts 탭 버튼 블록 내에 data-badge-count가 없어야 한다
        contacts_start = content.find('data-tab="contacts"')
        assert contacts_start != -1, "contacts tab button not found"
        contacts_end = content.find('data-tab="submissions"', contacts_start)
        contacts_block = content[contacts_start:contacts_end]
        assert "data-badge-count" not in contacts_block, "badge should not render when count=0"


# --- Workflow edge case tests (t25) ---


class TestWorkflowEdgeCases:
    """워크플로우 전환 엣지 케이스."""

    @pytest.mark.django_db
    def test_submission_create_duplicate_candidate_rejected(
        self, auth_client, project, candidate, interested_contact, user_with_org
    ):
        """같은 후보자에 대해 중복 Submission 생성 시도 시 에러.

        interested_contact fixture가 있어야 candidate가 SubmissionForm의
        queryset에 포함된다. 기존 Submission이 있으면 queryset에서 제외되어
        유효성 검사가 실패해야 한다.
        """
        Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "중복"},
        )
        # 유효성 검사 실패로 폼 재렌더링
        assert resp.status_code == 200
        assert "HX-Retarget" not in resp.headers
        # 중복이 실제로 방지되었는지 확인
        assert Submission.objects.filter(
            project=project, candidate=candidate
        ).count() == 1

    @pytest.mark.django_db
    def test_contact_update_interest_banner_disappears_on_tab_reload(
        self, auth_client, project, candidate, user_with_org
    ):
        """유도 배너는 일회성이다. 컨택 탭을 새로고침하면 배너가 없어야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # 컨택 탭 자체에는 배너가 없음 (배너는 contact_update 응답에만 포함)
        assert "interest-banner" not in content
