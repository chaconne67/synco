from unittest.mock import patch

import pytest

from candidates.models import Candidate, CandidateEmbedding, Category
from candidates.services.embedding import (
    build_embedding_text,
    generate_candidate_embedding,
)


@pytest.fixture
def category(db):
    return Category.objects.create(name="HR", name_ko="인사")


@pytest.fixture
def candidate(db, category):
    return Candidate.objects.create(
        name="홍길동",
        birth_year=1985,
        current_company="삼성전자",
        current_position="과장",
        total_experience_years=10,
        primary_category=category,
    )


@pytest.mark.django_db
def test_create_embedding(candidate):
    """CandidateEmbedding can store a 3072-dim vector."""
    vec = [0.1] * 3072
    emb = CandidateEmbedding.objects.create(
        candidate=candidate,
        embedding=vec,
        text_hash="abc123",
    )
    assert emb.pk is not None
    assert emb.candidate == candidate


@pytest.mark.django_db
def test_embedding_unique_per_candidate(candidate):
    """One candidate → one embedding (unique constraint)."""
    vec = [0.1] * 3072
    CandidateEmbedding.objects.create(
        candidate=candidate,
        embedding=vec,
        text_hash="abc123",
    )
    with pytest.raises(Exception):
        CandidateEmbedding.objects.create(
            candidate=candidate,
            embedding=vec,
            text_hash="def456",
        )


@pytest.mark.django_db
def test_pgvector_cosine_search(candidate, category):
    """Cosine similarity search returns nearest candidates."""
    vec_a = [1.0] + [0.0] * 3071
    vec_b = [0.0] + [1.0] + [0.0] * 3070

    CandidateEmbedding.objects.create(
        candidate=candidate, embedding=vec_a, text_hash="a"
    )

    candidate_b = Candidate.objects.create(
        name="김철수",
        primary_category=category,
    )
    CandidateEmbedding.objects.create(
        candidate=candidate_b, embedding=vec_b, text_hash="b"
    )

    query_vec = [0.9] + [0.1] + [0.0] * 3070
    results = CandidateEmbedding.objects.order_by(
        CandidateEmbedding.cosine_distance_expression(query_vec)
    )[:10]
    assert results[0].candidate == candidate


@pytest.mark.django_db
def test_build_embedding_text(candidate):
    """Build searchable text from candidate data."""
    text = build_embedding_text(candidate)
    assert "홍길동" in text
    assert "삼성전자" in text
    assert "과장" in text


@pytest.mark.django_db
@patch("candidates.services.embedding.get_embedding")
def test_generate_candidate_embedding(mock_embed, candidate):
    """Generate and save embedding for a candidate."""
    mock_embed.return_value = [0.5] * 3072
    emb = generate_candidate_embedding(candidate)
    assert emb is not None
    assert CandidateEmbedding.objects.filter(candidate=candidate).exists()
    mock_embed.assert_called_once()


@pytest.mark.django_db
@patch("candidates.services.embedding.get_embedding")
def test_generate_embedding_skips_if_unchanged(mock_embed, candidate):
    """Skip re-embedding if text hash unchanged."""
    mock_embed.return_value = [0.5] * 3072
    generate_candidate_embedding(candidate)
    generate_candidate_embedding(candidate)  # second call
    assert mock_embed.call_count == 1  # skipped
