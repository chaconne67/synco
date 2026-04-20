"""Dashboard view tests: auth, context, org isolation, HTMX partial."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from projects.models import ActionItem, ActionItemStatus

pytestmark = pytest.mark.django_db


class TestDashboardAuth:
    def test_unauthenticated_redirects(self):
        """Unauthenticated user -> login redirect."""
        c = Client()
        response = c.get(reverse("dashboard"))
        assert response.status_code == 302
        assert "/login" in response.url or "login" in response.url.lower()

    def test_authenticated_returns_200(self, logged_in_client):
        """Authenticated user -> 200 OK."""
        response = logged_in_client.get(reverse("dashboard"))
        assert response.status_code == 200


class TestDashboardOrgIsolation:
    def test_other_org_actions_not_visible(
        self, logged_in_client, application, user, other_org_user, action_type_reach_out
    ):
        """Actions from other orgs are not visible in dashboard."""
        from candidates.models import Candidate
        from clients.models import Client
        from projects.models import Application, Project, ProjectStatus

        # Create action for current user
        ActionItem.objects.create(
            application=application,
            action_type=action_type_reach_out,
            title="내 액션",
            status=ActionItemStatus.PENDING,
            assigned_to=user,
            due_at=timezone.now() + timedelta(hours=2),
            scheduled_at=timezone.now(),
        )

        # Create action for other org user
        other_org = other_org_user.membership.organization
        other_client = Client.objects.create(
            name="Other Client", organization=other_org
        )
        other_project = Project.objects.create(
            client=other_client,
            organization=other_org,
            title="Other Project",
            status=ProjectStatus.OPEN,
            created_by=other_org_user,
        )
        other_candidate = Candidate.objects.create(name="Other Candidate")
        other_app = Application.objects.create(
            project=other_project,
            candidate=other_candidate,
            created_by=other_org_user,
        )
        ActionItem.objects.create(
            application=other_app,
            action_type=action_type_reach_out,
            title="다른 조직 액션",
            status=ActionItemStatus.PENDING,
            assigned_to=other_org_user,
            due_at=timezone.now() + timedelta(hours=2),
            scheduled_at=timezone.now(),
        )

        response = logged_in_client.get(reverse("dashboard"))
        # Verify the "other org" action doesn't appear
        content = response.content.decode()
        assert "다른 조직 액션" not in content

    def test_only_assigned_actions_visible(
        self, logged_in_client, application, user, other_user, action_type_reach_out
    ):
        """Only actions assigned to the logged-in user appear."""
        # Create action assigned to other_user (same org)
        ActionItem.objects.create(
            application=application,
            action_type=action_type_reach_out,
            title="다른 사람 액션",
            status=ActionItemStatus.PENDING,
            assigned_to=other_user,
            due_at=timezone.now() + timedelta(hours=2),
            scheduled_at=timezone.now(),
        )

        response = logged_in_client.get(reverse("dashboard"))
        content = response.content.decode()
        assert "다른 사람 액션" not in content
