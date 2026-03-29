import hashlib
import logging

from common.embedding import get_embedding, get_embeddings_batch

logger = logging.getLogger(__name__)


def build_contact_text(contact) -> str:
    """Contact metadata + memo + recent interactions → single text for embedding.

    Max 2000 chars (Gemini 8192 token limit safety margin). Empty fields omitted.
    """
    parts = []

    # 1. Core metadata
    meta = " ".join(
        filter(
            None,
            [
                contact.name,
                contact.company_name,
                contact.industry,
                contact.region,
                contact.revenue_range,
            ],
        )
    )
    if meta:
        parts.append(meta)

    # 2. Memo (truncated)
    if contact.memo:
        parts.append(f"메모: {contact.memo[:200]}")

    # 3. Recent interactions (up to 5)
    recent = contact.interactions.order_by("-created_at").values_list("type", "summary")[:5]
    for itype, summary in recent:
        parts.append(f"- {itype}: {summary[:100]}")

    text = "\n".join(parts)
    return text[:2000]


def embed_contact(contact):
    """Create/update embedding for a single contact.

    Skips if source_hash unchanged. Returns ContactEmbedding or None on failure.
    """
    from intelligence.models import ContactEmbedding

    text = build_contact_text(contact)
    text_hash = hashlib.sha256(text.encode()).hexdigest()

    # Check existing
    try:
        existing = ContactEmbedding.objects.get(contact=contact)
        if existing.source_hash == text_hash:
            return existing  # No change
    except ContactEmbedding.DoesNotExist:
        existing = None

    vector = get_embedding(text)
    if vector is None:
        return existing  # Keep existing on failure

    emb, _ = ContactEmbedding.objects.update_or_create(
        contact=contact,
        defaults={
            "vector": vector,
            "source_text": text,
            "source_hash": text_hash,
        },
    )
    return emb


def embed_contacts_batch(contacts: list) -> list:
    """Batch embed N contacts. Chunks at 100 internally.

    Skips unchanged (source_hash match). Failed items skipped.
    Returns list of successful ContactEmbedding objects.
    """
    from intelligence.models import ContactEmbedding

    if not contacts:
        return []

    # Build texts and hashes
    texts = []
    hashes = []
    for c in contacts:
        t = build_contact_text(c)
        texts.append(t)
        hashes.append(hashlib.sha256(t.encode()).hexdigest())

    # Check existing hashes to skip unchanged
    existing_map = {
        ce.contact_id: ce
        for ce in ContactEmbedding.objects.filter(contact__in=contacts)
    }

    # Filter to only contacts that need embedding
    to_embed_indices = []
    for i, c in enumerate(contacts):
        existing = existing_map.get(c.pk)
        if existing and existing.source_hash == hashes[i]:
            continue  # Skip unchanged
        to_embed_indices.append(i)

    if not to_embed_indices:
        return list(existing_map.values())

    # Get embeddings for changed contacts only
    texts_to_embed = [texts[i] for i in to_embed_indices]
    vectors = get_embeddings_batch(texts_to_embed)

    results = []
    for j, idx in enumerate(to_embed_indices):
        vec = vectors[j]
        if vec is None:
            continue  # Skip failed
        contact = contacts[idx]
        emb, _ = ContactEmbedding.objects.update_or_create(
            contact=contact,
            defaults={
                "vector": vec,
                "source_text": texts[idx],
                "source_hash": hashes[idx],
            },
        )
        results.append(emb)

    # Include unchanged existing embeddings in results
    for i, c in enumerate(contacts):
        if i not in to_embed_indices:
            existing = existing_map.get(c.pk)
            if existing:
                results.append(existing)

    return results
