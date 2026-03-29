import logging

import numpy as np

from common.embedding import get_embedding, get_embeddings_batch

from ._references import cosine_similarity, get_sentiment_vectors

logger = logging.getLogger(__name__)

# Margin threshold: if max similarity - second is <= this, fallback to neutral
NEUTRAL_MARGIN = 0.01


def classify_sentiment(text: str, embedding: list[float] | None = None) -> str:
    """Single text → "positive"/"neutral"/"negative".

    Reuses embedding if provided. Returns "" on API failure.
    If caller already got None from get_embedding(), do NOT call this — skip instead.
    """
    refs = get_sentiment_vectors()
    if refs is None:
        return ""

    if embedding is None:
        embedding = get_embedding(text)
    if embedding is None:
        return ""

    vec = np.array(embedding)
    scores = {label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()}

    sorted_labels = sorted(scores, key=scores.get, reverse=True)
    top = sorted_labels[0]
    second = sorted_labels[1]

    if scores[top] - scores[second] <= NEUTRAL_MARGIN:
        return "neutral"
    return top


def classify_sentiments_batch(
    interactions: list,
    embeddings: list[list[float]] | None = None,
) -> None:
    """Batch classify sentiments for N interactions. Updates DB via bulk_update.

    Skips interactions that already have sentiment set.
    If embeddings provided, reuses them. Otherwise generates via API.
    """
    if not interactions:
        return

    refs = get_sentiment_vectors()
    if refs is None:
        return

    # Filter to unprocessed only
    to_process = [(i, idx) for idx, i in enumerate(interactions) if not i.sentiment]
    if not to_process:
        return

    # Get embeddings
    if embeddings is None:
        texts = [i.summary for i, _ in to_process]
        emb_list = get_embeddings_batch(texts)
    else:
        emb_list = [embeddings[idx] for _, idx in to_process]

    updated = []
    for (interaction, _), emb in zip(to_process, emb_list):
        if emb is None:
            continue
        sentiment = classify_sentiment(interaction.summary, embedding=emb)
        if sentiment:
            interaction.sentiment = sentiment
            updated.append(interaction)

    if updated:
        from contacts.models import Interaction

        Interaction.objects.bulk_update(updated, ["sentiment"])
