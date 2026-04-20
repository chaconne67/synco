"""P18: Identity matching tests — candidate identification (single-tenant)."""

import pytest

from candidates.models import Candidate
from projects.services.resume.identity import identify_candidate_for_org


@pytest.fixture
def candidate_with_email(db):
    return Candidate.objects.create(
        name="김철수",
        email="kim@example.com",
    )


@pytest.fixture
def candidate_with_phone(db):
    return Candidate.objects.create(
        name="박영희",
        phone="010-1234-5678",
        phone_normalized="01012345678",
    )


class TestEmailMatch:
    @pytest.mark.django_db
    def test_email_match_returns_candidate(self, candidate_with_email):
        extracted = {"name": "김철수", "email": "kim@example.com"}
        result = identify_candidate_for_org(extracted)
        assert result is not None
        assert result.candidate == candidate_with_email
        assert result.match_reason == "email"

    @pytest.mark.django_db
    def test_email_no_match_returns_none(self, candidate_with_email):
        extracted = {"name": "김철수", "email": "other@example.com"}
        result = identify_candidate_for_org(extracted)
        assert result is None

    @pytest.mark.django_db
    def test_email_case_insensitive(self, candidate_with_email):
        extracted = {"name": "김철수", "email": "KIM@EXAMPLE.COM"}
        result = identify_candidate_for_org(extracted)
        assert result is not None
        assert result.candidate == candidate_with_email


class TestPhoneMatch:
    @pytest.mark.django_db
    def test_phone_match_returns_candidate(self, candidate_with_phone):
        extracted = {"name": "박영희", "phone": "010-1234-5678"}
        result = identify_candidate_for_org(extracted)
        assert result is not None
        assert result.candidate == candidate_with_phone
        assert result.match_reason == "phone"

    @pytest.mark.django_db
    def test_phone_no_match_returns_none(self, candidate_with_phone):
        extracted = {"name": "박영희", "phone": "010-9999-9999"}
        result = identify_candidate_for_org(extracted)
        assert result is None


class TestNoNameBasedMatching:
    @pytest.mark.django_db
    def test_name_only_does_not_match(self, db):
        """Policy enforcement: name-only matching is not used."""
        Candidate.objects.create(name="이민수")
        extracted = {"name": "이민수"}
        result = identify_candidate_for_org(extracted)
        assert result is None

    @pytest.mark.django_db
    def test_name_with_different_email_does_not_match(self, db):
        Candidate.objects.create(name="이민수", email="lee@example.com")
        extracted = {"name": "이민수", "email": "different@example.com"}
        result = identify_candidate_for_org(extracted)
        assert result is None
