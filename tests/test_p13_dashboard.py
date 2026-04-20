"""P13: Dashboard tests."""

import pytest
from datetime import date, timedelta
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Contact, Project


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_owner(db, org):
    user = User.objects.create_user(username="owner13", password="test1234")
    Membership.objects.create(user=user, organization=org, role="owner")
    return user


@pytest.fixture
def user_consultant(db, org):
    user = User.objects.create_user(username="consultant13", password="test1234")
    Membership.objects.create(user=user, organization=org, role="consultant")
    return user


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT", organization=org)


@pytest.fixture
def project(org, client_obj, user_consultant):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="품질기획팀장",
        status="searching",
        created_by=user_consultant,
    )
    p.assigned_consultants.add(user_consultant)
    return p


@pytest.fixture
def auth_owner(user_owner):
    c = TestClient()
    c.login(username="owner13", password="test1234")
    return c


@pytest.fixture
def auth_consultant(user_consultant):
    c = TestClient()
    c.login(username="consultant13", password="test1234")
    return c


# --- Task 1: Model tests ---


class TestContactNextContactDate:
    @pytest.mark.django_db
    def test_next_contact_date_field_exists(self, project, user_consultant):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="홍길동",
            owned_by=project.organization,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now(),
            next_contact_date=date.today() + timedelta(days=3),
        )
        contact.refresh_from_db()
        assert contact.next_contact_date == date.today() + timedelta(days=3)

    @pytest.mark.django_db
    def test_next_contact_date_nullable(self, project, user_consultant):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="이순신",
            owned_by=project.organization,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now(),
        )
        contact.refresh_from_db()
        assert contact.next_contact_date is None


# --- Task 2: Urgency tests ---


class TestUrgencyScoring:
    @pytest.mark.django_db
    def test_recontact_today_is_priority_1(self, project, user_consultant):
        from candidates.models import Candidate
        from projects.services.urgency import compute_project_urgency

        candidate = Candidate.objects.create(
            name="홍길동", owned_by=project.organization
        )
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now() - timedelta(days=7),
            next_contact_date=date.today(),
        )
        action = compute_project_urgency(project)
        assert action is not None
        assert action["priority"] == 1
        assert action["level"] == "red"

    @pytest.mark.django_db
    def test_interview_tomorrow_is_priority_2(self, project, user_consultant):
        from candidates.models import Candidate
        from projects.models import Interview, Submission
        from projects.services.urgency import compute_project_urgency

        candidate = Candidate.objects.create(
            name="이순신", owned_by=project.organization
        )
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            status="통과",
        )
        Interview.objects.create(
            submission=sub,
            round=1,
            scheduled_at=timezone.now() + timedelta(hours=30),
            type="대면",
        )
        action = compute_project_urgency(project)
        assert action is not None
        assert action["priority"] == 2
        assert action["level"] == "red"

    @pytest.mark.django_db
    def test_collect_all_returns_multiple_actions(self, project, user_consultant):
        """Fix I-R1-01: collect_all_actions returns all priorities, not just max."""
        from candidates.models import Candidate
        from projects.models import Submission
        from projects.services.urgency import collect_all_actions

        candidate = Candidate.objects.create(
            name="홍길동", owned_by=project.organization
        )
        today = timezone.localdate()
        # Red action: recontact today (priority 1)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now() - timedelta(days=7),
            next_contact_date=today,
        )
        # Yellow action: use offer stale >7 days (priority 7) — not day-of-week sensitive
        candidate2 = Candidate.objects.create(
            name="김영희", owned_by=project.organization
        )
        sub = Submission.objects.create(
            project=project,
            candidate=candidate2,
            consultant=user_consultant,
            status="통과",
        )
        from projects.models import Offer

        offer = Offer.objects.create(
            submission=sub,
            status="협상중",
            salary="5000만원",
        )
        # Backdate created_at to >7 days ago (auto_now_add prevents setting at create)
        Offer.objects.filter(pk=offer.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )

        actions = collect_all_actions(project)
        levels = {a["level"] for a in actions}
        assert "red" in levels
        assert "yellow" in levels

    @pytest.mark.django_db
    def test_new_project_within_3days_is_priority_8(
        self, org, client_obj, user_consultant
    ):
        from projects.services.urgency import compute_project_urgency

        new_proj = Project.objects.create(
            client=client_obj,
            organization=org,
            title="신규 프로젝트",
            status="new",
            created_by=user_consultant,
        )
        action = compute_project_urgency(new_proj)
        assert action is not None
        assert action["priority"] == 8
        assert action["level"] == "green"

    @pytest.mark.django_db
    def test_closed_project_returns_none(self, org, client_obj, user_consultant):
        from projects.services.urgency import compute_project_urgency

        closed = Project.objects.create(
            client=client_obj,
            organization=org,
            title="종료 프로젝트",
            status="closed_success",
            created_by=user_consultant,
        )
        action = compute_project_urgency(closed)
        assert action is None


# --- Task 3: Dashboard service tests ---


class TestDashboardService:
    @pytest.mark.django_db
    def test_get_today_actions_returns_sorted_red_items(
        self, user_consultant, org, project
    ):
        from projects.services.dashboard import get_today_actions

        actions = get_today_actions(user_consultant, org)
        assert isinstance(actions, list)
        for action in actions:
            assert action["level"] == "red"
        priorities = [a["priority"] for a in actions]
        assert priorities == sorted(priorities)

    @pytest.mark.django_db
    def test_get_weekly_schedule_returns_yellow_items(
        self, user_consultant, org, project
    ):
        from projects.services.dashboard import get_weekly_schedule

        schedule = get_weekly_schedule(user_consultant, org)
        assert isinstance(schedule, list)
        for action in schedule:
            assert action["level"] == "yellow"

    @pytest.mark.django_db
    def test_get_pipeline_summary_counts(self, user_consultant, org, project):
        from projects.services.dashboard import get_pipeline_summary

        summary = get_pipeline_summary(user_consultant, org)
        assert "status_counts" in summary
        assert "total_active" in summary
        assert "month_closed" in summary
        assert summary["total_active"] >= 1

    @pytest.mark.django_db
    def test_get_pipeline_summary_org_isolation(self, user_consultant, org, project):
        from projects.services.dashboard import get_pipeline_summary

        other_org = Organization.objects.create(name="Other Org")
        other_client = Client.objects.create(
            name="Other", industry="IT", organization=other_org
        )
        Project.objects.create(
            client=other_client,
            organization=other_org,
            title="외부 프로젝트",
            status="searching",
            created_by=user_consultant,
        )
        summary = get_pipeline_summary(user_consultant, org)
        assert summary["total_active"] == 1

    @pytest.mark.django_db
    def test_get_recent_activities(self, user_consultant, org, project):
        from projects.services.dashboard import get_recent_activities

        activities = get_recent_activities(user_consultant, org, limit=10)
        assert isinstance(activities, list)

    @pytest.mark.django_db
    def test_get_team_summary_excludes_viewer(self, user_owner, org, project):
        """Fix I-R1-02: viewer role should not appear in team summary."""
        from projects.services.dashboard import get_team_summary

        viewer = User.objects.create_user(username="viewer13", password="test1234")
        Membership.objects.create(user=viewer, organization=org, role="viewer")

        summary = get_team_summary(user_owner, org)
        usernames = [c["user"].username for c in summary["consultants"]]
        assert "viewer13" not in usernames

    @pytest.mark.django_db
    def test_get_pending_approvals_empty(self, org):
        from projects.services.dashboard import get_pending_approvals

        qs = get_pending_approvals(org)
        assert qs.count() == 0


# --- Task 5: Routing + view tests ---


class TestDashboardViews:
    @pytest.mark.django_db
    def test_dashboard_requires_login(self):
        c = TestClient()
        resp = c.get("/dashboard/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_root_redirects_to_dashboard(self, auth_consultant):
        resp = auth_consultant.get("/")
        assert resp.status_code == 302
        assert "/dashboard/" in resp.url

    @pytest.mark.django_db
    def test_dashboard_explicit_url(self, auth_consultant):
        resp = auth_consultant.get("/dashboard/")
        assert resp.status_code == 200
        assert "대시보드" in resp.content.decode()

    @pytest.mark.django_db
    def test_dashboard_no_membership_redirects_to_invite(self):
        """No membership -> redirect to invite page."""
        user = User.objects.create_user(username="nomem_dash", password="test1234")
        c = TestClient()
        c.force_login(user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 302
        assert "/accounts/invite/" in resp.url

    @pytest.mark.django_db
    def test_dashboard_pending_redirects_to_pending(self):
        """Pending membership -> redirect to pending page."""
        org = Organization.objects.create(name="Pending Org")
        user = User.objects.create_user(username="pend_dash", password="test1234")
        Membership.objects.create(user=user, organization=org, status="pending")
        c = TestClient()
        c.force_login(user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 302
        assert "/accounts/pending/" in resp.url

    @pytest.mark.django_db
    def test_dashboard_rejected_redirects_to_rejected(self):
        """Rejected membership -> redirect to rejected page."""
        org = Organization.objects.create(name="Rejected Org")
        user = User.objects.create_user(username="rej_dash", password="test1234")
        Membership.objects.create(user=user, organization=org, status="rejected")
        c = TestClient()
        c.force_login(user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 302
        assert "/accounts/rejected/" in resp.url

    @pytest.mark.django_db
    def test_unauthenticated_root_redirects_to_login(self):
        c = TestClient()
        resp = c.get("/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url
