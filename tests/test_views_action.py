"""ActionItem view tests: CRUD, HTMX contracts, auth, org isolation."""

import pytest
from django.test import Client
from django.urls import reverse

from projects.models import ActionItem, ActionItemStatus
from projects.services.action_lifecycle import complete_action, create_action

pytestmark = pytest.mark.django_db


class TestActionCreate:
    def test_action_create_get_renders_modal(self, logged_in_client, application):
        """GET action_create -> renders modal with action types."""
        response = logged_in_client.get(
            reverse("projects:action_create", args=[application.pk])
        )
        assert response.status_code == 200
        assert "action_types" in response.context

    def test_action_create_post(
        self, logged_in_client, application, action_type_reach_out
    ):
        """POST action_create -> ActionItem created + HX-Trigger."""
        response = logged_in_client.post(
            reverse("projects:action_create", args=[application.pk]),
            data={
                "action_type_id": str(action_type_reach_out.pk),
                "title": "테스트 액션",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 204
        assert response["HX-Trigger"] == "actionChanged"
        assert ActionItem.objects.filter(
            application=application, action_type=action_type_reach_out
        ).exists()


class TestActionComplete:
    def test_action_complete_post(
        self, logged_in_client, application, action_type_reach_out
    ):
        """POST complete -> action done + appropriate response."""
        action = create_action(application, action_type_reach_out, None)
        response = logged_in_client.post(
            reverse("projects:action_complete", args=[action.pk]),
            data={"result": "성공적 연락"},
            HTTP_HX_REQUEST="true",
        )
        # Could be 200 (with suggest_next modal) or 204
        assert response.status_code in (200, 204)
        action.refresh_from_db()
        assert action.status == ActionItemStatus.DONE

    def test_action_complete_get_renders_modal(
        self, logged_in_client, application, action_type_reach_out
    ):
        """GET complete -> renders complete modal."""
        action = create_action(application, action_type_reach_out, None)
        response = logged_in_client.get(
            reverse("projects:action_complete", args=[action.pk])
        )
        assert response.status_code == 200

    def test_complete_already_done_returns_error(
        self, logged_in_client, application, action_type_reach_out
    ):
        """Completing already-done action -> error (not 500)."""
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None)
        response = logged_in_client.post(
            reverse("projects:action_complete", args=[action.pk]),
            data={"result": "again"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400


class TestActionSkip:
    def test_action_skip_post(
        self, logged_in_client, application, action_type_reach_out
    ):
        """POST skip -> action skipped + HX-Trigger."""
        action = create_action(application, action_type_reach_out, None)
        response = logged_in_client.post(
            reverse("projects:action_skip", args=[action.pk]),
            data={"note": "skip reason"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 204
        assert response["HX-Trigger"] == "actionChanged"
        action.refresh_from_db()
        assert action.status == ActionItemStatus.SKIPPED


class TestActionReschedule:
    def test_action_reschedule_post(
        self, logged_in_client, application, action_type_reach_out
    ):
        """POST reschedule -> due_at updated + HX-Trigger."""
        action = create_action(application, action_type_reach_out, None)
        new_due = "2026-04-20T10:00:00"
        response = logged_in_client.post(
            reverse("projects:action_reschedule", args=[action.pk]),
            data={"new_due_at": new_due},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 204
        assert response["HX-Trigger"] == "actionChanged"


class TestActionProposeNext:
    def test_propose_next_creates_actions(
        self, logged_in_client, application, action_type_reach_out, user
    ):
        """POST propose_next with selected types -> creates new ActionItems."""
        action = create_action(application, action_type_reach_out, user)
        complete_action(action, user)

        # Get suggested next types
        from projects.services.action_lifecycle import propose_next

        suggestions = propose_next(action)
        if not suggestions:
            pytest.skip("No suggestions for reach_out -> cannot test propose_next")

        selected_id = str(suggestions[0].pk)
        response = logged_in_client.post(
            reverse("projects:action_propose_next", args=[action.pk]),
            data={"next_action_type_ids": [selected_id]},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        # New action should be created
        assert ActionItem.objects.filter(
            application=application,
            parent_action=action,
        ).exists()

    def test_propose_next_empty_selection(
        self, logged_in_client, application, action_type_reach_out, user
    ):
        """POST propose_next with no selection -> 204."""
        action = create_action(application, action_type_reach_out, user)
        complete_action(action, user)

        response = logged_in_client.post(
            reverse("projects:action_propose_next", args=[action.pk]),
            data={},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 204


class TestActionOrgIsolation:
    def test_other_org_action_404(
        self, other_org_client, application, action_type_reach_out
    ):
        """Accessing action from other org -> 404."""
        action = create_action(application, action_type_reach_out, None)
        response = other_org_client.get(
            reverse("projects:action_complete", args=[action.pk])
        )
        assert response.status_code == 404


class TestActionAuthEdge:
    def test_unauthenticated_action_raises(self, application, action_type_reach_out):
        """Unauthenticated user accessing action -> 500 (missing @login_required).
        Phase 6 should add @login_required to Phase 3b views.
        """
        action = create_action(application, action_type_reach_out, None)
        c = Client(raise_request_exception=False)
        response = c.post(
            reverse("projects:action_complete", args=[action.pk]),
            data={"result": "test"},
        )
        # Documents current behavior; Phase 6 will fix.
        assert response.status_code == 500
