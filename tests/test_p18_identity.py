"""P18: Identity matching tests — org-scoped candidate identification."""

import pytest

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from projects.services.resume.identity import identify_candidate_for_org


@pytest.fixture
def org_a(db):
    return Organization.objects.create(name="Org A")


@pytest.fixture
def org_b(db):
    return Organization.objects.create(name="Org B")


@pytest.fixture
def user_a(db, org_a):
    u = User.objects.create_user(username="user_a", password="testpass123")
    Membership.objects.create(user=u, organization=org_a)
    return u


@pytest.fixture
def user_b(db, org_b):
    u = User.objects.create_user(username="user_b", password="testpass123")
    Membership.objects.create(user=u, organization=org_b)
    return u


class TestCrossOrgCollision:
    def test_cross_org_email_no_match(self, org_a, org_b):
        """Candidate owned by org A with same email — org B upload should not match."""
        Candidate.objects.create(
            name="김철수",
            email="kim@example.com",
            owned_by=org_a,
        )
        extracted = {"name": "김철수", "email": "kim@example.com"}
        result = identify_candidate_for_org(extracted, org_b)
        assert result is None

    def test_same_org_email_match(self, org_a):
        """Candidate owned by org A with same email — org A upload should match."""
        candidate = Candidate.objects.create(
            name="김철수",
            email="kim@example.com",
            owned_by=org_a,
        )
        extracted = {"name": "김철수", "email": "kim@example.com"}
        result = identify_candidate_for_org(extracted, org_a)
        assert result is not None
        assert result.candidate == candidate
        assert result.match_reason == "email"


class TestPhoneNormalizationMatch:
    def test_phone_match_within_org(self, org_a):
        candidate = Candidate.objects.create(
            name="박영희",
            phone="010-1234-5678",
            phone_normalized="01012345678",
            owned_by=org_a,
        )
        extracted = {"name": "박영희", "phone": "010-1234-5678"}
        result = identify_candidate_for_org(extracted, org_a)
        assert result is not None
        assert result.candidate == candidate
        assert result.match_reason == "phone"

    def test_phone_cross_org_no_match(self, org_a, org_b):
        Candidate.objects.create(
            name="박영희",
            phone="010-1234-5678",
            phone_normalized="01012345678",
            owned_by=org_a,
        )
        extracted = {"name": "박영희", "phone": "010-1234-5678"}
        result = identify_candidate_for_org(extracted, org_b)
        assert result is None


class TestNoNameBasedMatching:
    def test_name_only_does_not_match(self, org_a):
        """Policy enforcement: name-only matching is not used."""
        Candidate.objects.create(
            name="이민수",
            owned_by=org_a,
        )
        extracted = {"name": "이민수"}
        result = identify_candidate_for_org(extracted, org_a)
        assert result is None

    def test_name_with_different_email_does_not_match(self, org_a):
        Candidate.objects.create(
            name="이민수",
            email="lee@example.com",
            owned_by=org_a,
        )
        extracted = {"name": "이민수", "email": "different@example.com"}
        result = identify_candidate_for_org(extracted, org_a)
        assert result is None
