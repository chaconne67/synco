import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy-initialize Gemini client. No API call at import time."""
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def get_embedding(text: str) -> list[float] | None:
    """Single text → 3072-dim vector. One Gemini API call.
    Returns None on failure (caller handles)."""
    try:
        client = _get_client()
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
        )
        return response.embeddings[0].values
    except Exception:
        logger.exception("Gemini embedding failed for text[:50]=%s", text[:50])
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """N texts → N vectors. Chunks internally at 100.
    Partial failures: failed indices are None.
    Return list length always equals input texts length."""
    if not texts:
        return []

    results: list[list[float] | None] = [None] * len(texts)
    chunk_size = 100

    for start in range(0, len(texts), chunk_size):
        chunk = texts[start : start + chunk_size]
        try:
            client = _get_client()
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=chunk,
            )
            for i, emb in enumerate(response.embeddings):
                results[start + i] = emb.values
        except Exception:
            logger.exception(
                "Gemini batch embedding failed for chunk [%d:%d]",
                start,
                start + len(chunk),
            )
            # Failed indices remain None

    return results
