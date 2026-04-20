"""Tests for candidate comment system."""

from unittest.mock import patch

import pytest
from django.test import Client

from candidates.models import Candidate, CandidateComment, REASON_CODES


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(username="tester", password="testpass123", level=1)


@pytest.fixture
def candidate(db):
    return Candidate.objects.create(
        name="홍길동",
        email="hong@test.com",
    )


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="tester", password="testpass123")
    return c


class TestCommentCreate:
    def test_create_comment_updates_recommendation(self, client, candidate):
        """POST creates comment and updates candidate recommendation_status."""
        assert candidate.recommendation_status == "pending"

        resp = client.post(
            f"/candidates/{candidate.pk}/comments/",
            {
                "recommendation_status": "not_recommended",
                "reason_codes": ["edu_undergrad_missing", "career_deleted"],
                "content": "인터뷰 결과 학부 미기재 확인",
                "input_method": "text",
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200

        candidate.refresh_from_db()
        assert candidate.recommendation_status == "not_recommended"

        comment = CandidateComment.objects.get(candidate=candidate)
        assert comment.recommendation_status == "not_recommended"
        assert comment.reason_codes == ["edu_undergrad_missing", "career_deleted"]
        assert comment.content == "인터뷰 결과 학부 미기재 확인"
        assert comment.input_method == "text"
        assert comment.author.username == "tester"

    def test_multiple_comments_ordering(self, client, candidate):
        """Comments are ordered by most recent first."""
        client.post(
            f"/candidates/{candidate.pk}/comments/",
            {"recommendation_status": "on_hold", "content": "첫 번째"},
            HTTP_HX_REQUEST="true",
        )
        client.post(
            f"/candidates/{candidate.pk}/comments/",
            {"recommendation_status": "not_recommended", "content": "두 번째"},
            HTTP_HX_REQUEST="true",
        )

        comments = list(CandidateComment.objects.filter(candidate=candidate))
        assert len(comments) == 2
        assert comments[0].content == "두 번째"
        assert comments[1].content == "첫 번째"

        candidate.refresh_from_db()
        assert candidate.recommendation_status == "not_recommended"

    def test_invalid_status_defaults_to_pending(self, client, candidate):
        """Invalid recommendation_status falls back to pending."""
        client.post(
            f"/candidates/{candidate.pk}/comments/",
            {"recommendation_status": "invalid_value", "content": "test"},
            HTTP_HX_REQUEST="true",
        )

        candidate.refresh_from_db()
        assert candidate.recommendation_status == "pending"

    def test_unauthenticated_redirects(self, candidate):
        """Unauthenticated user gets redirected."""
        c = Client()
        resp = c.post(
            f"/candidates/{candidate.pk}/comments/",
            {"recommendation_status": "recommended"},
        )
        assert resp.status_code == 302

    def test_get_not_allowed(self, client, candidate):
        """GET method returns 405."""
        resp = client.get(f"/candidates/{candidate.pk}/comments/")
        assert resp.status_code == 405


class TestReasonCodes:
    def test_reason_labels_property(self, db, candidate, user):
        comment = CandidateComment.objects.create(
            candidate=candidate,
            author=user,
            recommendation_status="not_recommended",
            reason_codes=["edu_undergrad_missing", "career_deleted"],
            content="test",
        )
        labels = comment.reason_labels
        assert labels == [
            REASON_CODES["edu_undergrad_missing"],
            REASON_CODES["career_deleted"],
        ]

    def test_empty_reason_codes(self, db, candidate, user):
        comment = CandidateComment.objects.create(
            candidate=candidate,
            author=user,
            recommendation_status="recommended",
            reason_codes=[],
        )
        assert comment.reason_labels == []


class TestStatusIndependence:
    """D3.3: recommendation_status changes must not affect validation_status."""

    def test_comment_does_not_change_validation_status(self, client, candidate):
        """Changing recommendation_status leaves validation_status unchanged."""
        original_validation = candidate.validation_status

        client.post(
            f"/candidates/{candidate.pk}/comments/",
            {"recommendation_status": "not_recommended", "content": "test"},
            HTTP_HX_REQUEST="true",
        )

        candidate.refresh_from_db()
        assert candidate.recommendation_status == "not_recommended"
        assert candidate.validation_status == original_validation


class TestTransactionAtomicity:
    """D3.4: comment creation + status update must be atomic."""

    def test_rollback_on_save_failure(self, client, candidate):
        """If candidate.save() fails, comment should not be created."""
        original_status = candidate.recommendation_status

        with patch.object(Candidate, "save", side_effect=Exception("DB error")):
            try:
                client.post(
                    f"/candidates/{candidate.pk}/comments/",
                    {"recommendation_status": "recommended", "content": "test"},
                    HTTP_HX_REQUEST="true",
                )
            except Exception:
                pass

        assert CandidateComment.objects.filter(candidate=candidate).count() == 0
        candidate.refresh_from_db()
        assert candidate.recommendation_status == original_status
