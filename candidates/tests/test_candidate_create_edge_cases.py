import pytest
from candidates.models import Candidate
from candidates.services.candidate_create import find_duplicate


@pytest.mark.django_db
def test_duplicate_empty_phone_normalized():
    """Phone field with only spaces should not match."""
    Candidate.objects.all().delete()
    result = find_duplicate(None, "   ")
    assert result is None


@pytest.mark.django_db
def test_duplicate_short_phone():
    """Phone with < 8 digits should not match via last-8 check."""
    Candidate.objects.all().delete()
    result = find_duplicate(None, "123-456")
    assert result is None


@pytest.mark.django_db
def test_duplicate_exact_phone_match():
    """Exact phone number match via last-8."""
    Candidate.objects.all().delete()
    c = Candidate.objects.create(name="기존", phone="010-1234-5678")
    # Same number should match
    result = find_duplicate(None, "010-1234-5678")
    assert result is not None
    assert result.pk == c.pk


@pytest.mark.django_db
def test_duplicate_normalized_phone_match():
    """Normalized phone (no dashes) should match."""
    Candidate.objects.all().delete()
    c = Candidate.objects.create(name="기존", phone="010-1234-5678")
    # Same number without dashes
    result = find_duplicate(None, "01012345678")
    assert result is not None
    assert result.pk == c.pk


@pytest.mark.django_db
def test_duplicate_different_last_8_no_match():
    """Different last-8 digits should not match."""
    Candidate.objects.all().delete()
    Candidate.objects.create(name="기존", phone="010-1234-5678")
    # Different last-8
    result = find_duplicate(None, "010-9999-9999")
    assert result is None


@pytest.mark.django_db
def test_duplicate_case_insensitive_email():
    """Email matching should be case-insensitive."""
    Candidate.objects.all().delete()
    c = Candidate.objects.create(name="기존", email="Test@Example.COM")
    # Different case
    result = find_duplicate("test@example.com", None)
    assert result is not None
    assert result.pk == c.pk


@pytest.mark.django_db
def test_duplicate_email_with_spaces():
    """Email with spaces should be stripped."""
    Candidate.objects.all().delete()
    c = Candidate.objects.create(name="기존", email="test@example.com")
    # Spaces around
    result = find_duplicate("  test@example.com  ", None)
    assert result is not None
    assert result.pk == c.pk


@pytest.mark.django_db
def test_duplicate_prefers_email_over_phone():
    """Email match should be checked first."""
    Candidate.objects.all().delete()
    c1 = Candidate.objects.create(name="기존1", email="test@example.com")
    Candidate.objects.create(name="기존2", phone="010-5678-9012")
    # Both provided, should match email first
    result = find_duplicate("test@example.com", "010-5678-9012")
    assert result.pk == c1.pk
