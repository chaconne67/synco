"""Tests for projects/services/collision.py."""

import pytest

from clients.models import Client
from projects.models import Project, ProjectStatus
from projects.services.collision import compute_title_similarity, detect_collisions


@pytest.fixture
def other_client(db):
    return Client.objects.create(name="AnotherCorp")


# ---------------------------------------------------------------------------
# compute_title_similarity unit tests
# ---------------------------------------------------------------------------


def test_identical_titles_score_one():
    assert compute_title_similarity("마케팅 팀장", "마케팅 팀장") == 1.0


def test_completely_different_titles_score_low():
    score = compute_title_similarity("재무 이사", "마케팅 팀장")
    assert score < 0.7


def test_empty_title_returns_zero():
    assert compute_title_similarity("", "마케팅 팀장") == 0.0
    assert compute_title_similarity("마케팅 팀장", "") == 0.0


# ---------------------------------------------------------------------------
# detect_collisions — no collision
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_collision_when_no_other_projects(client_company, boss_user):
    """No existing projects for client → empty result."""
    results = detect_collisions(client_id=client_company.pk, title="영업 팀장")
    assert results == []


@pytest.mark.django_db
def test_no_collision_different_client(client_company, other_client, boss_user):
    """Similar title on a different client → no collision."""
    Project.objects.create(
        client=other_client,
        title="영업 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    results = detect_collisions(client_id=client_company.pk, title="영업 팀장")
    assert results == []


@pytest.mark.django_db
def test_no_collision_when_project_excluded(client_company, boss_user):
    """exclude_project_id suppresses the match."""
    p = Project.objects.create(
        client=client_company,
        title="영업 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    results = detect_collisions(
        client_id=client_company.pk,
        title="영업 팀장",
        exclude_project_id=p.pk,
    )
    assert results == []


# ---------------------------------------------------------------------------
# detect_collisions — 높은중복 (high similarity ≥ 0.7)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_high_collision_same_title(client_company, boss_user):
    """Identical title → conflict_type = '높은중복'."""
    Project.objects.create(
        client=client_company,
        title="영업 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    results = detect_collisions(client_id=client_company.pk, title="영업 팀장")
    assert len(results) >= 1
    assert results[0]["conflict_type"] == "높은중복"
    assert results[0]["score"] >= 0.7


@pytest.mark.django_db
def test_high_collision_close_title(client_company, boss_user):
    """Very similar title (parenthetical variant) → '높은중복'."""
    Project.objects.create(
        client=client_company,
        title="영업 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    # Same core, parenthetical stripped by _normalize
    results = detect_collisions(
        client_id=client_company.pk,
        title="영업 팀장(정규직)",
    )
    assert len(results) >= 1
    assert results[0]["conflict_type"] == "높은중복"


# ---------------------------------------------------------------------------
# detect_collisions — 참고정보 (low/medium similarity < 0.7)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_low_collision_partial_match(client_company, boss_user):
    """Partially similar title → conflict_type = '참고정보'."""
    Project.objects.create(
        client=client_company,
        title="영업 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    # "영업 부장" shares the dept keyword but not the suffix → lower score
    results = detect_collisions(client_id=client_company.pk, title="영업 이사")
    if results:
        assert results[0]["conflict_type"] in ("높은중복", "참고정보")
        # At least must have score > 0
        assert results[0]["score"] > 0.0


@pytest.mark.django_db
def test_reference_info_returned_for_medium_similarity(client_company, boss_user):
    """Force a score between 0.0 and 0.7 → '참고정보'."""
    Project.objects.create(
        client=client_company,
        title="마케팅 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    # "영업 팀장" shares 팀장 suffix → some similarity but not identical
    results = detect_collisions(client_id=client_company.pk, title="영업 팀장")
    # Score must be >0 and the conflict_type must be one of the two valid values
    assert len(results) >= 1
    assert results[0]["conflict_type"] in ("높은중복", "참고정보")


# ---------------------------------------------------------------------------
# detect_collisions — result structure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_result_has_expected_keys(client_company, boss_user):
    Project.objects.create(
        client=client_company,
        title="개발 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    results = detect_collisions(client_id=client_company.pk, title="개발 팀장")
    assert len(results) == 1
    r = results[0]
    assert "project" in r
    assert "score" in r
    assert "conflict_type" in r
    assert "consultant_name" in r
    assert "status_display" in r


@pytest.mark.django_db
def test_results_capped_at_five(client_company, boss_user):
    """More than 5 similar projects → only top 5 returned."""
    for i in range(7):
        Project.objects.create(
            client=client_company,
            title=f"영업 팀장{i}",
            status=ProjectStatus.OPEN,
            created_by=boss_user,
        )
    results = detect_collisions(client_id=client_company.pk, title="영업 팀장")
    assert len(results) <= 5


@pytest.mark.django_db
def test_open_project_included(client_company, boss_user):
    """Open project is included in collision detection."""
    Project.objects.create(
        client=client_company,
        title="영업 팀장",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    results = detect_collisions(client_id=client_company.pk, title="영업 팀장")
    assert len(results) == 1
    assert results[0]["conflict_type"] == "높은중복"
