"""Shared reference vector management for sentiment and task detection.

Lazy initialization + file cache. No API call at import time.
Cache invalidation: sentence hash comparison detects code changes.
"""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np

from common.embedding import get_embeddings_batch

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".cache")
SENTIMENT_CACHE = CACHE_DIR / "sentiment_refs.json"
TASK_CACHE = CACHE_DIR / "task_refs.json"

SENTIMENT_REFS = {
    "positive": "고객이 적극적으로 관심을 보이며 계약을 논의하고 다음 미팅을 요청했다",
    "neutral": "일반적인 안부 통화를 했고 특별한 진전은 없었다",
    "negative": "고객이 명확하게 거절했고 더 이상 연락을 원하지 않는다고 했다",
}

TASK_REFS = {
    "task": "견적서를 보내기로 약속했고 다음주까지 회신해야 한다",
    "followup": "다시 연락하기로 했고 자료를 준비해서 전달해야 한다",
    "promise": "보험 상품 비교표를 만들어서 보내주기로 했다",
    "waiting": "좋은 내용이지만 지금은 상황이 안 되고 나중에 연락하겠다고 했다",
    "not_task": "일반적인 안부를 나누었고 특별한 약속은 없었다",
}

# Module-level cache (populated on first use)
_sentiment_vectors: dict[str, np.ndarray] | None = None
_task_vectors: dict[str, np.ndarray] | None = None


def _compute_hash(refs: dict[str, str]) -> str:
    text = json.dumps(refs, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _load_cache(
    cache_path: Path, refs: dict[str, str]
) -> dict[str, list[float]] | None:
    if not cache_path.exists():
        return None
    try:
        with open(cache_path) as f:
            data = json.load(f)
        if data.get("hash") != _compute_hash(refs):
            return None  # Refs changed, invalidate
        return data["vectors"]
    except Exception:
        return None


def _save_cache(
    cache_path: Path, refs: dict[str, str], vectors: dict[str, list[float]]
):
    CACHE_DIR.mkdir(exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({"hash": _compute_hash(refs), "vectors": vectors}, f)


def _init_vectors(
    refs: dict[str, str], cache_path: Path
) -> dict[str, np.ndarray] | None:
    """Initialize reference vectors from cache or API."""
    # Try file cache
    cached = _load_cache(cache_path, refs)
    if cached:
        return {k: np.array(v) for k, v in cached.items()}

    # Generate via API
    keys = list(refs.keys())
    texts = [refs[k] for k in keys]
    embeddings = get_embeddings_batch(texts)

    if any(e is None for e in embeddings):
        logger.warning("Some reference embeddings failed, skipping initialization")
        return None

    vectors = {k: np.array(embeddings[i]) for i, k in enumerate(keys)}

    # Save to file cache
    _save_cache(cache_path, refs, {k: embeddings[i] for i, k in enumerate(keys)})

    return vectors


def get_sentiment_vectors() -> dict[str, np.ndarray] | None:
    """Get sentiment reference vectors. Lazy init + file cache."""
    global _sentiment_vectors
    if _sentiment_vectors is None:
        _sentiment_vectors = _init_vectors(SENTIMENT_REFS, SENTIMENT_CACHE)
    return _sentiment_vectors


def get_task_vectors() -> dict[str, np.ndarray] | None:
    """Get task detection reference vectors. Lazy init + file cache."""
    global _task_vectors
    if _task_vectors is None:
        _task_vectors = _init_vectors(TASK_REFS, TASK_CACHE)
    return _task_vectors


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
