"""P01: Models and App Foundation tests.

Tests for clients, projects, accounts (Organization/Membership/TelegramBinding),
and Candidate.owned_by FK.
"""

import uuid

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, User
from candidates.models import Candidate
from clients.models import (
    Client,
    CompanyProfile,
    Contract,
    PreferredCert,
    UniversityTier,
)
from projects.models import (
    Contact,
    Interview,
    Notification,
    Offer,
    Project,
    ProjectApproval,
    ProjectContext,
    ProjectStatus,
    Submission,
)


# --- Helpers ---


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def user2(db):
    return User.objects.create_user(username="testuser2", password="testpass123")


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def organization2(db):
    return Organization.objects.create(name="Other Firm")


@pytest.fixture
def client(organization):
    return Client.objects.create(name="Acme Corp", organization=organization)


@pytest.fixture
def candidate(db):
    return Candidate.objects.create(name="John Doe")


@pytest.fixture
def project(client, organization, user):
    return Project.objects.create(
        client=client,
        organization=organization,
        title="Senior Developer",
        created_by=user,
    )


@pytest.fixture
def submission(project, candidate, user):
    return Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
    )


# --- UUID PK tests ---


class TestUUIDPrimaryKeys:
    @pytest.mark.django_db
    def test_organization_has_uuid_pk(self, organization):
        assert isinstance(organization.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_membership_has_uuid_pk(self, user, organization):
        m = Membership.objects.create(
            user=user, organization=organization, role="consultant"
        )
        assert isinstance(m.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_client_has_uuid_pk(self, client):
        assert isinstance(client.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_project_has_uuid_pk(self, project):
        assert isinstance(project.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_contract_has_uuid_pk(self, client):
        c = Contract.objects.create(
            client=client, start_date="2026-01-01", status="체결"
        )
        assert isinstance(c.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_university_tier_has_uuid_pk(self):
        u = UniversityTier.objects.create(name="Seoul National", tier="SKY")
        assert isinstance(u.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_notification_has_uuid_pk(self, user):
        n = Notification.objects.create(
            recipient=user,
            type="reminder",
            title="Test",
            body="Body",
        )
        assert isinstance(n.pk, uuid.UUID)


# --- Organization ---


class TestOrganization:
    @pytest.mark.django_db
    def test_create_organization(self):
        org = Organization.objects.create(name="HH Partners", plan="premium")
        assert org.name == "HH Partners"
        assert org.plan == "premium"
        assert org.db_share_enabled is False
        assert isinstance(org.pk, uuid.UUID)

    @pytest.mark.django_db
    def test_organization_default_plan(self):
        org = Organization.objects.create(name="New Firm")
        assert org.plan == "basic"

    @pytest.mark.django_db
    def test_organization_str(self, organization):
        assert str(organization) == "Test Firm"


# --- Membership ---


class TestMembership:
    @pytest.mark.django_db
    def test_create_membership(self, user, organization):
        m = Membership.objects.create(
            user=user, organization=organization, role="owner"
        )
        assert m.user == user
        assert m.organization == organization
        assert m.role == "owner"

    @pytest.mark.django_db
    def test_membership_default_role(self, user, organization):
        m = Membership.objects.create(user=user, organization=organization)
        assert m.role == "consultant"

    @pytest.mark.django_db
    def test_membership_one_to_one_constraint(self, user, organization, organization2):
        Membership.objects.create(user=user, organization=organization, role="owner")
        with pytest.raises(IntegrityError):
            Membership.objects.create(
                user=user, organization=organization2, role="consultant"
            )

    @pytest.mark.django_db
    def test_membership_reverse_access(self, user, organization):
        Membership.objects.create(user=user, organization=organization, role="owner")
        assert user.membership.organization == organization


# --- TelegramBinding ---


class TestTelegramBinding:
    @pytest.mark.django_db
    def test_create_telegram_binding(self, user):
        tb = TelegramBinding.objects.create(user=user, chat_id="123456789")
        assert tb.chat_id == "123456789"
        assert tb.is_active is True

    @pytest.mark.django_db
    def test_telegram_one_to_one(self, user):
        TelegramBinding.objects.create(user=user, chat_id="111")
        with pytest.raises(IntegrityError):
            TelegramBinding.objects.create(user=user, chat_id="222")


# --- Client ---


class TestClient:
    @pytest.mark.django_db
    def test_create_client(self, organization):
        c = Client.objects.create(
            name="Samsung",
            industry="Electronics",
            size="대기업",
            region="Seoul",
            organization=organization,
        )
        assert c.name == "Samsung"
        assert c.size == "대기업"
        assert c.contact_persons == []
        assert c.organization == organization

    @pytest.mark.django_db
    def test_client_contact_persons_json(self, organization):
        persons = [
            {"name": "Kim", "email": "kim@example.com", "phone": "010-1234-5678"}
        ]
        c = Client.objects.create(
            name="Naver",
            contact_persons=persons,
            organization=organization,
        )
        c.refresh_from_db()
        assert c.contact_persons == persons

    @pytest.mark.django_db
    def test_client_str(self, client):
        assert str(client) == "Acme Corp"

    @pytest.mark.django_db
    def test_client_organization_fk(self, client, organization):
        assert client.organization == organization
        assert client in organization.clients.all()


# --- Contract ---


class TestContract:
    @pytest.mark.django_db
    def test_create_contract(self, client):
        c = Contract.objects.create(
            client=client,
            start_date="2026-01-01",
            end_date="2026-12-31",
            terms="Standard terms",
            status="체결",
        )
        assert c.client == client
        assert c.status == "체결"

    @pytest.mark.django_db
    def test_contract_default_status(self, client):
        c = Contract.objects.create(client=client, start_date="2026-01-01")
        assert c.status == "협의중"


# --- UniversityTier ---


class TestUniversityTier:
    @pytest.mark.django_db
    def test_create_university_tier(self):
        u = UniversityTier.objects.create(
            name="서울대학교",
            name_en="Seoul National University",
            tier="SKY",
            ranking=1,
        )
        assert u.name == "서울대학교"
        assert u.tier == "SKY"
        assert u.country == "KR"

    @pytest.mark.django_db
    def test_overseas_tier(self):
        u = UniversityTier.objects.create(name="MIT", tier="OVERSEAS_TOP", country="US")
        assert u.tier == "OVERSEAS_TOP"
        assert u.country == "US"


# --- CompanyProfile ---


class TestCompanyProfile:
    @pytest.mark.django_db
    def test_create_company_profile(self):
        cp = CompanyProfile.objects.create(
            name="Google", industry="IT", size_category="대기업"
        )
        assert cp.name == "Google"
        assert str(cp) == "Google"


# --- PreferredCert ---


class TestPreferredCert:
    @pytest.mark.django_db
    def test_create_preferred_cert(self):
        pc = PreferredCert.objects.create(name="CPA", category="회계/재무")
        assert pc.name == "CPA"
        assert pc.category == "회계/재무"

    @pytest.mark.django_db
    def test_preferred_cert_unique_name(self):
        PreferredCert.objects.create(name="CPA", category="회계/재무")
        with pytest.raises(IntegrityError):
            PreferredCert.objects.create(name="CPA", category="IT")


# --- Project ---


class TestProject:
    @pytest.mark.django_db
    def test_create_project(self, client, organization, user):
        p = Project.objects.create(
            client=client,
            organization=organization,
            title="Backend Engineer",
            created_by=user,
        )
        assert p.title == "Backend Engineer"
        assert p.status == ProjectStatus.NEW
        assert p.client == client
        assert p.organization == organization

    @pytest.mark.django_db
    def test_project_status_choices(self, project):
        project.status = ProjectStatus.SEARCHING
        project.save()
        project.refresh_from_db()
        assert project.status == "searching"

    @pytest.mark.django_db
    def test_project_assigned_consultants_m2m(self, project, user, user2):
        project.assigned_consultants.add(user, user2)
        assert project.assigned_consultants.count() == 2

    @pytest.mark.django_db
    def test_project_fk_to_client(self, project, client):
        assert project.client == client
        assert project in client.projects.all()

    @pytest.mark.django_db
    def test_project_fk_to_organization(self, project, organization):
        assert project.organization == organization
        assert project in organization.projects.all()


# --- Contact ---


class TestContact:
    @pytest.mark.django_db
    def test_create_contact(self, project, candidate, user):
        c = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        assert c.project == project
        assert c.candidate == candidate
        assert c.channel == "전화"
        assert c.result == "응답"

    @pytest.mark.django_db
    def test_contact_locked_until(self, project, candidate, user):
        lock_time = timezone.now()
        c = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel="카톡",
            contacted_at=timezone.now(),
            result="관심",
            locked_until=lock_time,
        )
        assert c.locked_until == lock_time


# --- Submission ---


class TestSubmission:
    @pytest.mark.django_db
    def test_create_submission(self, submission):
        assert submission.status == "작성중"
        assert submission.submitted_at is None

    @pytest.mark.django_db
    def test_submission_status_update(self, submission):
        submission.status = "제출"
        submission.submitted_at = timezone.now()
        submission.save()
        submission.refresh_from_db()
        assert submission.status == "제출"
        assert submission.submitted_at is not None


# --- Interview ---


class TestInterview:
    @pytest.mark.django_db
    def test_create_interview(self, submission):
        i = Interview.objects.create(
            submission=submission,
            round=1,
            scheduled_at=timezone.now(),
            type="대면",
        )
        assert i.round == 1
        assert i.result == "대기"

    @pytest.mark.django_db
    def test_multiple_rounds(self, submission):
        Interview.objects.create(
            submission=submission, round=1, scheduled_at=timezone.now(), type="화상"
        )
        Interview.objects.create(
            submission=submission, round=2, scheduled_at=timezone.now(), type="대면"
        )
        assert submission.interviews.count() == 2


# --- Offer ---


class TestOffer:
    @pytest.mark.django_db
    def test_create_offer(self, submission):
        o = Offer.objects.create(
            submission=submission,
            salary="8000만원",
            position_title="시니어 개발자",
            status="협상중",
        )
        assert o.salary == "8000만원"
        assert o.status == "협상중"
        assert o.terms == {}

    @pytest.mark.django_db
    def test_offer_one_to_one(self, submission):
        Offer.objects.create(submission=submission, status="협상중")
        with pytest.raises(IntegrityError):
            Offer.objects.create(submission=submission, status="수락")


# --- ProjectApproval ---


class TestProjectApproval:
    @pytest.mark.django_db
    def test_create_approval(self, project, user):
        a = ProjectApproval.objects.create(
            project=project,
            requested_by=user,
            message="Please approve",
        )
        assert a.status == "대기"
        assert a.decided_by is None
        assert a.decided_at is None

    @pytest.mark.django_db
    def test_approval_with_conflict(self, client, organization, user):
        p1 = Project.objects.create(
            client=client, organization=organization, title="P1", created_by=user
        )
        p2 = Project.objects.create(
            client=client, organization=organization, title="P2", created_by=user
        )
        a = ProjectApproval.objects.create(
            project=p1,
            requested_by=user,
            conflict_project=p2,
        )
        assert a.conflict_project == p2


# --- ProjectContext ---


class TestProjectContext:
    @pytest.mark.django_db
    def test_create_context(self, project, user):
        ctx = ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="searching",
            pending_action="call_candidate",
            draft_data={"notes": "test"},
        )
        assert ctx.last_step == "searching"
        assert ctx.draft_data == {"notes": "test"}


# --- Notification ---


class TestNotification:
    @pytest.mark.django_db
    def test_create_notification(self, user):
        n = Notification.objects.create(
            recipient=user,
            type="approval_request",
            title="New Approval",
            body="Please review",
        )
        assert n.status == "pending"
        assert n.recipient == user

    @pytest.mark.django_db
    def test_notification_callback_data(self, user):
        n = Notification.objects.create(
            recipient=user,
            type="auto_generated",
            title="Auto",
            body="Generated",
            callback_data={"action": "approve", "id": "123"},
        )
        n.refresh_from_db()
        assert n.callback_data["action"] == "approve"


# --- Candidate.owned_by ---


class TestCandidateOwnedBy:
    @pytest.mark.django_db
    def test_candidate_owned_by_null(self, candidate):
        assert candidate.owned_by is None

    @pytest.mark.django_db
    def test_candidate_owned_by_set(self, candidate, organization):
        candidate.owned_by = organization
        candidate.save()
        candidate.refresh_from_db()
        assert candidate.owned_by == organization

    @pytest.mark.django_db
    def test_candidate_owned_by_reverse(self, organization):
        Candidate.objects.create(name="A", owned_by=organization)
        Candidate.objects.create(name="B", owned_by=organization)
        assert organization.owned_candidates.count() == 2
        assert set(organization.owned_candidates.values_list("name", flat=True)) == {
            "A",
            "B",
        }

    @pytest.mark.django_db
    def test_candidate_owned_by_org_delete_sets_null(self, organization):
        c = Candidate.objects.create(name="Test", owned_by=organization)
        organization.delete()
        c.refresh_from_db()
        assert c.owned_by is None


# --- FK relationship integrity ---


class TestFKRelationships:
    @pytest.mark.django_db
    def test_project_to_client(self, project, client):
        assert project.client_id == client.pk

    @pytest.mark.django_db
    def test_contact_to_project_and_candidate(self, project, candidate, user):
        c = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel="이메일",
            contacted_at=timezone.now(),
            result="미응답",
        )
        assert c.project_id == project.pk
        assert c.candidate_id == candidate.pk

    @pytest.mark.django_db
    def test_submission_to_project(self, submission, project):
        assert submission.project_id == project.pk

    @pytest.mark.django_db
    def test_interview_to_submission(self, submission):
        i = Interview.objects.create(
            submission=submission,
            round=1,
            scheduled_at=timezone.now(),
            type="전화",
        )
        assert i.submission_id == submission.pk

    @pytest.mark.django_db
    def test_offer_to_submission(self, submission):
        o = Offer.objects.create(submission=submission)
        assert o.submission_id == submission.pk

    @pytest.mark.django_db
    def test_client_to_organization(self, client, organization):
        assert client.organization_id == organization.pk

    @pytest.mark.django_db
    def test_cascade_delete_client_deletes_projects(self, client, project):
        assert Project.objects.filter(pk=project.pk).exists()
        client.delete()
        assert not Project.objects.filter(pk=project.pk).exists()
