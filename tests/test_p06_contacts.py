"""P06: Contact management tests.

Tests for contact CRUD, reservation (locking), duplicate checking,
lock release, organization isolation, and search tab integration.
"""

from datetime import timedelta

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project
from projects.services.contact import (
    check_duplicate,
    release_expired_reservations,
    reserve_candidates,
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
def user2_with_org(db, org):
    """Same org, second user (non-assigned consultant)."""
    user = User.objects.create_user(username="tester3", password="test1234")
    Membership.objects.create(user=user, organization=org)
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
def auth_client3(user2_with_org):
    """Same org, non-assigned consultant client."""
    c = TestClient()
    c.login(username="tester3", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT", organization=org)


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp", industry="Finance", organization=org2
    )


@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="Test Project",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project2(client_obj, org, user_with_org):
    """Same org, different project."""
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="Other Project",
        created_by=user_with_org,
    )


@pytest.fixture
def project_other_org(client_obj2, org2, user_with_org2):
    return Project.objects.create(
        client=client_obj2,
        organization=org2,
        title="Other Org Project",
        created_by=user_with_org2,
    )


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


@pytest.fixture
def candidate2(org):
    return Candidate.objects.create(name="김철수", owned_by=org)


@pytest.fixture
def candidate_other_org(org2):
    return Candidate.objects.create(name="이영희", owned_by=org2)


# --- Service: check_duplicate ---


class TestCheckDuplicate:
    def test_blocking_interested(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=now,
            result="관심",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is True

    def test_blocking_rejected(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=now,
            result="거절",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is True

    def test_warning_no_response(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=now,
            result="미응답",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert len(result["warnings"]) == 1

    def test_warning_responded(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=now,
            result="응답",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert len(result["warnings"]) == 1

    def test_no_duplicate(self, project, candidate):
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert len(result["warnings"]) == 0
        assert len(result["other_projects"]) == 0

    def test_reserved_shows_warning(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=7),
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert any("컨택 예정" in w for w in result["warnings"])

    def test_other_project_shown(self, project, project2, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project2,
            candidate=candidate,
            consultant=user_with_org,
            channel="이메일",
            contacted_at=now,
            result="응답",
        )
        result = check_duplicate(project, candidate)
        assert len(result["other_projects"]) == 1


# --- Service: reserve_candidates ---


class TestReserveCandidates:
    def test_create(self, project, candidate, user_with_org):
        result = reserve_candidates(project, [candidate.pk], user_with_org)
        assert len(result["created"]) == 1
        contact = result["created"][0]
        assert contact.result == "예정"
        assert contact.locked_until is not None
        assert contact.locked_until > timezone.now()

    def test_skip_existing_reservation(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=7),
        )
        result = reserve_candidates(project, [candidate.pk], user_with_org)
        assert len(result["skipped"]) == 1
        assert len(result["created"]) == 0

    def test_skip_blocking_result(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",
        )
        result = reserve_candidates(project, [candidate.pk], user_with_org)
        assert len(result["skipped"]) == 1
        assert len(result["created"]) == 0

    def test_multiple_candidates(self, project, candidate, candidate2, user_with_org):
        result = reserve_candidates(
            project, [candidate.pk, candidate2.pk], user_with_org
        )
        assert len(result["created"]) == 2


# --- Service: release_expired ---


class TestReleaseExpired:
    def test_release(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() - timedelta(days=1),
        )
        count = release_expired_reservations()
        assert count == 1
        contact = Contact.objects.get(project=project, candidate=candidate)
        assert contact.locked_until is None

    def test_keep_valid(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=3),
        )
        count = release_expired_reservations()
        assert count == 0


# --- View: contact_create ---


class TestContactCreateView:
    def test_get_form(self, auth_client, project):
        resp = auth_client.get(f"/projects/{project.pk}/contacts/new/")
        assert resp.status_code == 200

    def test_post_success(self, auth_client, project, candidate):
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {
                "candidate": candidate.pk,
                "channel": "전화",
                "contacted_at": "2026-04-08T10:00",
                "result": "응답",
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert Contact.objects.filter(project=project, candidate=candidate).exists()

    def test_blocked_duplicate(self, auth_client, project, candidate, user_with_org):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {
                "candidate": candidate.pk,
                "channel": "이메일",
                "contacted_at": "2026-04-09T10:00",
                "result": "응답",
            },
            HTTP_HX_REQUEST="true",
        )
        # form re-rendered with error
        assert resp.status_code == 200
        assert Contact.objects.filter(project=project, candidate=candidate).count() == 1

    def test_auto_release_reservation(
        self, auth_client, project, candidate, user_with_org
    ):
        """Creating a real contact releases existing reservation."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {
                "candidate": candidate.pk,
                "channel": "전화",
                "contacted_at": "2026-04-08T10:00",
                "result": "응답",
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        # Reservation should have locked_until cleared
        reserved = Contact.objects.filter(
            project=project, candidate=candidate, result="예정"
        ).first()
        if reserved:
            assert reserved.locked_until is None

    def test_requires_login(self, project):
        c = TestClient()
        resp = c.get(f"/projects/{project.pk}/contacts/new/")
        assert resp.status_code == 302


# --- View: contact_update ---


class TestContactUpdateView:
    def test_update(self, auth_client, project, candidate, user_with_org):
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="미응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": candidate.pk,
                "channel": "전화",
                "contacted_at": "2026-04-08T10:00",
                "result": "응답",
                "notes": "통화 완료",
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact.refresh_from_db()
        assert contact.result == "응답"
        assert contact.notes == "통화 완료"


# --- View: contact_delete ---


class TestContactDeleteView:
    def test_delete(self, auth_client, project, candidate, user_with_org):
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="미응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/delete/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert not Contact.objects.filter(pk=contact.pk).exists()


# --- View: contact_reserve ---


class TestContactReserveView:
    def test_reserve(self, auth_client, project, candidate):
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact = Contact.objects.get(project=project, candidate=candidate)
        assert contact.result == "예정"
        assert contact.locked_until > timezone.now()

    def test_reserve_no_candidates(self, auth_client, project):
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/reserve/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 400


# --- View: contact_release_lock ---


class TestContactReleaseLockView:
    def test_release_by_assigned(self, auth_client, project, candidate, user_with_org):
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/release/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact.refresh_from_db()
        assert contact.locked_until is None

    def test_release_denied_non_consultant(
        self, auth_client3, project, candidate, user_with_org
    ):
        """Same org but non-assigned consultant cannot release."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client3.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/release/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 403


# --- Organization Isolation ---


class TestContactOrgIsolation:
    def test_create_other_org_404(self, auth_client, project_other_org):
        resp = auth_client.get(f"/projects/{project_other_org.pk}/contacts/new/")
        assert resp.status_code == 404

    def test_reserve_other_org_404(self, auth_client, project_other_org, candidate):
        resp = auth_client.post(
            f"/projects/{project_other_org.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
        )
        assert resp.status_code == 404

    def test_tab_contacts_other_org_404(self, auth_client, project_other_org):
        resp = auth_client.get(
            f"/projects/{project_other_org.pk}/tab/contacts/",
        )
        assert resp.status_code == 404

    def test_check_duplicate_other_org_404(self, auth_client, project_other_org):
        resp = auth_client.get(
            f"/projects/{project_other_org.pk}/contacts/check-duplicate/",
        )
        assert resp.status_code == 404


# --- Tab Content ---


class TestContactTabContent:
    def test_separates_completed_and_reserved(
        self, auth_client, project, candidate, candidate2, user_with_org
    ):
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        Contact.objects.create(
            project=project,
            candidate=candidate2,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert candidate.name in content
        assert candidate2.name in content

    def test_empty_contacts(self, auth_client, project):
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert "컨택 이력이 없습니다" in resp.content.decode()
