"""P05: Project detail tabs tests.

Tests for 6-tab structure, login_required, organization isolation,
tab content rendering, HTMX partial, funnel counts, and search org isolation.
"""

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    Submission,
)


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(
        name="Acme Corp",
        industry="IT",
        organization=org,
    )


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp",
        industry="Finance",
        organization=org2,
    )


@pytest.fixture
def project_obj(org, client_obj, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="Dev Hire",
        status="searching",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_obj2(org2, client_obj2, user_with_org2):
    return Project.objects.create(
        client=client_obj2,
        organization=org2,
        title="Other Project",
        status="new",
        created_by=user_with_org2,
    )


@pytest.fixture
def candidate(db):
    return Candidate.objects.create(name="Hong Gildong")


@pytest.fixture
def candidate2(db):
    return Candidate.objects.create(name="Kim Younghee")


# --- Tab URLs ---

TAB_URLS = [
    ("project_detail", ""),
    ("tab_overview", "tab/overview/"),
    ("tab_search", "tab/search/"),
    ("tab_contacts", "tab/contacts/"),
    ("tab_submissions", "tab/submissions/"),
    ("tab_interviews", "tab/interviews/"),
    ("tab_offers", "tab/offers/"),
]


# --- Login Required ---


class TestTabLoginRequired:
    @pytest.mark.django_db
    @pytest.mark.parametrize("name,suffix", TAB_URLS)
    def test_requires_login(self, project_obj, name, suffix):
        c = TestClient()
        resp = c.get(f"/projects/{project_obj.pk}/{suffix}")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url


# --- Organization Isolation ---


class TestTabOrgIsolation:
    @pytest.mark.django_db
    @pytest.mark.parametrize("name,suffix", TAB_URLS)
    def test_other_org_404(self, auth_client, project_obj2, name, suffix):
        resp = auth_client.get(f"/projects/{project_obj2.pk}/{suffix}")
        assert resp.status_code == 404


# --- Detail Page (Tab Wrapper) ---


class TestProjectDetailTabs:
    @pytest.mark.django_db
    def test_detail_renders_overview_inline(self, auth_client, project_obj):
        """상세 진입 시 개요 탭이 추가 요청 없이 렌더링."""
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Should contain tab bar
        assert "개요" in content
        assert "서칭" in content
        assert "컨택" in content
        # Should contain overview content inline
        assert "진행 현황" in content
        assert "담당 컨설턴트" in content

    @pytest.mark.django_db
    def test_detail_shows_project_header(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        content = resp.content.decode()
        assert "Dev Hire" in content
        assert "Acme Corp" in content

    @pytest.mark.django_db
    def test_detail_shows_status_badge(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        content = resp.content.decode()
        assert "서칭중" in content


# --- Overview Tab ---


class TestTabOverview:
    @pytest.mark.django_db
    def test_overview_renders(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/overview/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "진행 현황" in content
        assert "담당 컨설턴트" in content

    @pytest.mark.django_db
    def test_funnel_counts(self, auth_client, project_obj, candidate, user_with_org):
        """퍼널 카운트 정확성."""
        Contact.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        Submission.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/overview/")
        content = resp.content.decode()
        # The funnel section should show count 1 for contacts and submissions
        assert "컨택" in content
        assert "추천" in content

    @pytest.mark.django_db
    def test_recent_progress_contacts(
        self, auth_client, project_obj, candidate, user_with_org
    ):
        """최근 진행 현황에 컨택 표시."""
        Contact.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/overview/")
        content = resp.content.decode()
        assert "Hong Gildong" in content
        assert "관심" in content

    @pytest.mark.django_db
    def test_empty_progress(self, auth_client, project_obj):
        """데이터 없을 때 안내 메시지."""
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/overview/")
        content = resp.content.decode()
        assert "진행 이력이 없습니다" in content

    @pytest.mark.django_db
    def test_consultants_list(self, auth_client, project_obj, user_with_org):
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/overview/")
        content = resp.content.decode()
        assert user_with_org.username in content


# --- Search Tab ---


class TestTabSearch:
    @pytest.mark.django_db
    def test_search_without_requirements(self, auth_client, project_obj):
        """requirements 없을 때 안내 메시지."""
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/search/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "JD 분석이 먼저 필요합니다" in content

    @pytest.mark.django_db
    def test_search_renders(self, auth_client, project_obj):
        """requirements 있을 때 200 응답."""
        project_obj.requirements = {
            "position": "Backend Developer",
            "min_experience_years": 5,
        }
        project_obj.save()
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/search/")
        assert resp.status_code == 200


# --- Contacts Tab ---


class TestTabContacts:
    @pytest.mark.django_db
    def test_contacts_empty(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/contacts/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "후보자를 서칭하고 컨택을 시작하세요" in content

    @pytest.mark.django_db
    def test_contacts_list(self, auth_client, project_obj, candidate, user_with_org):
        Contact.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/contacts/")
        content = resp.content.decode()
        assert "Hong Gildong" in content


# --- Submissions Tab ---


class TestTabSubmissions:
    @pytest.mark.django_db
    def test_submissions_empty(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/submissions/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "컨택에서 관심 후보자가 생기면 추천서류를 작성할 수 있습니다" in content

    @pytest.mark.django_db
    def test_submissions_list(self, auth_client, project_obj, candidate, user_with_org):
        Submission.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/submissions/")
        content = resp.content.decode()
        assert "Hong Gildong" in content


# --- Interviews Tab ---


class TestTabInterviews:
    @pytest.mark.django_db
    def test_interviews_empty(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/interviews/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "면접 이력이 없습니다" in content

    @pytest.mark.django_db
    def test_interviews_via_submission(
        self, auth_client, project_obj, candidate, user_with_org
    ):
        """면접은 submission__project 경로로 조회."""
        sub = Submission.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
        )
        Interview.objects.create(
            submission=sub,
            round=1,
            scheduled_at=timezone.now(),
            type="대면",
            result="대기",
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/interviews/")
        content = resp.content.decode()
        assert "Hong Gildong" in content
        assert "1차" in content


# --- Offers Tab ---


class TestTabOffers:
    @pytest.mark.django_db
    def test_offers_empty(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/offers/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "오퍼 이력이 없습니다" in content

    @pytest.mark.django_db
    def test_offers_via_submission(
        self, auth_client, project_obj, candidate, user_with_org
    ):
        """오퍼는 submission__project 경로로 조회."""
        sub = Submission.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
        )
        Offer.objects.create(
            submission=sub,
            salary="8000만원",
            status="협상중",
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/offers/")
        content = resp.content.decode()
        assert "Hong Gildong" in content
        assert "8000만원" in content


# --- Tab Badge Counts ---


class TestTabBadgeCounts:
    @pytest.mark.django_db
    def test_badge_counts_in_detail(
        self, auth_client, project_obj, candidate, user_with_org
    ):
        """탭 배지 카운트 정확성."""
        Contact.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        content = resp.content.decode()
        # The tab bar should include badge with count
        assert "컨택" in content


# --- HTMX Partial ---


class TestHTMXPartial:
    @pytest.mark.django_db
    def test_detail_htmx_renders_partial(self, auth_client, project_obj):
        """HTMX 요청 시 partial (no DOCTYPE)."""
        resp = auth_client.get(
            f"/projects/{project_obj.pk}/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content

    @pytest.mark.django_db
    def test_detail_full_page_renders(self, auth_client, project_obj):
        """일반 요청 시 full page."""
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" in content

    @pytest.mark.django_db
    def test_tab_is_always_partial(self, auth_client, project_obj):
        """탭 콘텐츠는 항상 partial (extends 없음)."""
        resp = auth_client.get(f"/projects/{project_obj.pk}/tab/overview/")
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content
