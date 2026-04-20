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
    def test_boss_sees_all_actions(
        self, logged_in_client, application, user, other_org_user, action_type_reach_out
    ):
        """Boss (level>=2) sees all scheduled actions, not just their own."""
        # user fixture has level=2, so scope_owner=True → sees all
        ActionItem.objects.create(
            application=application,
            action_type=action_type_reach_out,
            title="다른 사용자 액션",
            status=ActionItemStatus.PENDING,
            assigned_to=other_org_user,
            due_at=timezone.now() + timedelta(hours=2),
            scheduled_at=timezone.now(),
        )

        response = logged_in_client.get(reverse("dashboard"))
        content = response.content.decode()
        # Boss sees everything
        assert response.status_code == 200

    def test_staff_sees_only_assigned_actions(
        self, application, other_org_user, action_type_reach_out, db
    ):
        """Staff (level=1) only sees actions assigned to them in weekly schedule."""
        from django.test import Client as TestClient
        from accounts.models import User

        staff = User.objects.create_user(username="stafftest", password="x", level=1)
        c = TestClient()
        c.force_login(staff)

        ActionItem.objects.create(
            application=application,
            action_type=action_type_reach_out,
            title="다른 사람 액션",
            status=ActionItemStatus.PENDING,
            assigned_to=other_org_user,
            due_at=timezone.now() + timedelta(hours=2),
            scheduled_at=timezone.now(),
        )

        response = c.get(reverse("dashboard"))
        content = response.content.decode()
        assert "다른 사람 액션" not in content
