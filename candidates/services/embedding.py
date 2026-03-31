"""Generate and manage candidate embeddings for semantic search."""

import hashlib

from candidates.models import Candidate, CandidateEmbedding
from common.embedding import get_embedding


def build_embedding_text(candidate: Candidate) -> str:
    """Build a searchable text representation of a candidate for embedding."""
    parts = [candidate.name]

    if candidate.current_company:
        parts.append(
            f"현재 {candidate.current_company} {candidate.current_position or ''}"
        )

    if candidate.total_experience_years:
        parts.append(f"경력 {candidate.total_experience_years}년")

    if candidate.summary:
        parts.append(candidate.summary)

    for career in candidate.careers.all()[:5]:
        line = career.company
        if career.position:
            line += f" {career.position}"
        if career.department:
            line += f" {career.department}"
        if career.duties:
            line += f" {career.duties[:100]}"
        parts.append(line)

    for edu in candidate.educations.all():
        line = edu.institution
        if edu.degree:
            line += f" {edu.degree}"
        if edu.major:
            line += f" {edu.major}"
        parts.append(line)

    for cert in candidate.certifications.all():
        parts.append(cert.name)

    if candidate.core_competencies:
        parts.extend(candidate.core_competencies[:10])

    for cat in candidate.categories.all():
        parts.append(cat.name)

    return " ".join(parts)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def generate_candidate_embedding(candidate: Candidate) -> CandidateEmbedding | None:
    """Generate embedding for a candidate. Skips if text unchanged."""
    text = build_embedding_text(candidate)
    h = _text_hash(text)

    existing = CandidateEmbedding.objects.filter(candidate=candidate).first()
    if existing and existing.text_hash == h:
        return existing

    vec = get_embedding(text)
    if vec is None:
        return None

    if existing:
        existing.embedding = vec
        existing.text_hash = h
        existing.save(update_fields=["embedding", "text_hash", "updated_at"])
        return existing

    return CandidateEmbedding.objects.create(
        candidate=candidate,
        embedding=vec,
        text_hash=h,
    )
