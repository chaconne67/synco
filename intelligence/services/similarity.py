import logging

import numpy as np
from pgvector.django import CosineDistance

from ._references import cosine_similarity

logger = logging.getLogger(__name__)


def find_similar_contacts(contact, n=5) -> list[tuple]:
    """Find similar contacts via pgvector cosine distance.

    Returns [(Contact, similarity_score), ...] where similarity is 0~1.
    Returns empty list if contact has no embedding.
    """
    from intelligence.models import ContactEmbedding

    try:
        emb = ContactEmbedding.objects.get(contact=contact)
    except ContactEmbedding.DoesNotExist:
        return []

    # pgvector cosine distance query
    similar = (
        ContactEmbedding.objects.filter(contact__fc=contact.fc)
        .exclude(contact=contact)
        .annotate(distance=CosineDistance("vector", emb.vector))
        .order_by("distance")[:n]
        .select_related("contact")
    )

    results = []
    for s in similar:
        similarity = 1 - s.distance  # cosine distance → similarity
        results.append((s.contact, similarity))

    return results


def find_contacts_like(
    reference_tier="gold", target_tier="yellow", fc=None, n=10
) -> list[dict]:
    """Find target_tier contacts similar to reference_tier centroid.

    Fallback: gold → green → empty list.

    Returns list of dicts:
      - contact: Contact object
      - similarity: float (0~1)
      - exemplar: Contact (reference tier contact most similar to this candidate)
    """
    from intelligence.models import ContactEmbedding

    if fc is None:
        return []

    def _get_ref_embeddings(tier):
        return list(
            ContactEmbedding.objects.filter(
                contact__fc=fc,
                contact__relationship_tier=tier,
            ).select_related("contact")
        )

    # Fallback chain: gold → green → empty
    ref_embeddings = _get_ref_embeddings(reference_tier)
    if not ref_embeddings and reference_tier == "gold":
        ref_embeddings = _get_ref_embeddings("green")
    if not ref_embeddings:
        return []

    # Compute centroid of reference embeddings
    ref_vectors = np.array([e.vector for e in ref_embeddings])
    centroid = ref_vectors.mean(axis=0)

    # Get target tier contacts with embeddings
    target_embeddings = list(
        ContactEmbedding.objects.filter(
            contact__fc=fc,
            contact__relationship_tier=target_tier,
        ).select_related("contact")
    )
    # Also include red tier if target is yellow
    if target_tier == "yellow":
        red_embeddings = list(
            ContactEmbedding.objects.filter(
                contact__fc=fc,
                contact__relationship_tier="red",
            ).select_related("contact")
        )
        target_embeddings.extend(red_embeddings)

    if not target_embeddings:
        return []

    # Rank by similarity to centroid
    scored = []
    for te in target_embeddings:
        sim = cosine_similarity(np.array(te.vector), centroid)
        scored.append((te, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_n = scored[:n]

    # For each candidate, find the most similar exemplar from reference tier
    ref_contact_vectors = [(e.contact, np.array(e.vector)) for e in ref_embeddings]

    results = []
    for te, similarity in top_n:
        candidate_vec = np.array(te.vector)
        best_exemplar = None
        best_sim = -1
        for ref_contact, ref_vec in ref_contact_vectors:
            sim = cosine_similarity(candidate_vec, ref_vec)
            if sim > best_sim:
                best_sim = sim
                best_exemplar = ref_contact

        results.append(
            {
                "contact": te.contact,
                "similarity": similarity,
                "exemplar": best_exemplar,
            }
        )

    return results
