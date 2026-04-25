"""Institution name resolver — UniversityTier master lookup + LLM fallback.

Goal: bridge LLM non-determinism in institution naming (한↔영, 약어, 한+영 병기,
띄어쓰기 변형) by mapping every variant to a canonical UniversityTier entry.

Usage:
    from clients.services.institution_resolver import resolve_institution
    canonical_name = resolve_institution("Dongguk University")
    # → "동국대학교" (UniversityTier에서 찾음 또는 LLM 매핑 후 자동 등록)

Flow:
    1. Local cache (per-process, lru_cache) hit → return immediately
    2. UniversityTier exact lookup (name / name_en / aliases, normalized)
    3. UniversityTier substring fallback (한+영 병기 케이스 처리)
    4. LLM mapping → UniversityTier에 신규 등록
    5. LLM 신뢰도 낮으면 원문 유지 (needs_review 큐)
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from django.db import transaction

logger = logging.getLogger(__name__)


# ===========================================================================
# Normalization
# ===========================================================================


def _strip_korean_spaces(s: str) -> str:
    """Remove whitespace between Hangul characters only."""
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", s)


def normalize_for_match(s: str) -> str:
    """Normalize institution name to a comparison key.

    - lowercase
    - collapse whitespace
    - strip 한글 사이 공백
    - strip trailing punctuation/parens
    """
    if not s:
        return ""
    norm = re.sub(r"\s+", " ", s.strip().lower())
    norm = _strip_korean_spaces(norm)
    return norm


def _candidate_keys(raw_name: str) -> list[str]:
    """Generate candidate normalized keys for a raw institution name.

    Includes original, no-paren version, and bilingual paren contents.
    Used for matching against UniversityTier (name, name_en, aliases).
    """
    norm = normalize_for_match(raw_name)
    if not norm:
        return []
    keys = [norm]
    no_paren = re.sub(r"\s*\([^)]*\)\s*$", "", norm).strip()
    if no_paren and no_paren != norm:
        keys.append(no_paren)
    paren_match = re.search(r"\(([^)]+)\)", norm)
    if paren_match:
        inner = _strip_korean_spaces(paren_match.group(1).strip())
        if inner and inner not in keys:
            keys.append(inner)
    return keys


# ===========================================================================
# UniversityTier lookup
# ===========================================================================


def _build_lookup_index() -> dict[str, str]:
    """Build {normalized_key → canonical_name} index from UniversityTier rows.

    Includes name, name_en, and each alias as keys mapping to canonical name.
    Index is rebuilt lazily; new entries created during resolve flow invalidate
    via _invalidate_lookup_index().
    """
    from clients.models import UniversityTier

    index: dict[str, str] = {}
    for row in UniversityTier.objects.all():
        canonical = row.name
        for raw in (row.name, row.name_en, *(row.aliases or [])):
            if not raw:
                continue
            for key in _candidate_keys(raw):
                index.setdefault(key, canonical)
    return index


_LOOKUP_INDEX_CACHE: dict[str, str] | None = None


def _get_lookup_index() -> dict[str, str]:
    global _LOOKUP_INDEX_CACHE
    if _LOOKUP_INDEX_CACHE is None:
        _LOOKUP_INDEX_CACHE = _build_lookup_index()
    return _LOOKUP_INDEX_CACHE


def _invalidate_lookup_index() -> None:
    global _LOOKUP_INDEX_CACHE
    _LOOKUP_INDEX_CACHE = None
    _resolve_cached.cache_clear()


def _master_lookup(raw_name: str) -> str | None:
    """Try to map raw_name to a canonical UniversityTier name."""
    if not raw_name:
        return None
    index = _get_lookup_index()
    # 1) exact match on any candidate key
    for key in _candidate_keys(raw_name):
        if key in index:
            return index[key]
    # 2) substring fallback — index key contained in raw norm
    raw_norm = normalize_for_match(raw_name)
    if not raw_norm:
        return None
    for key, canonical in index.items():
        if len(key) >= 5 and key in raw_norm:
            return canonical
    return None


# ===========================================================================
# LLM mapping
# ===========================================================================


_LLM_MAPPING_PROMPT = """이 학교 이름을 표준 형식으로 매핑하세요.

입력: "{raw_name}"

다음 JSON 형식으로 응답하세요 (다른 설명 없이 JSON만):
{{
  "canonical_name": "한국 대학이면 한글 정식 명칭, 해외 대학이면 원어 정식 명칭",
  "name_en": "영문 표기 (한국 대학) 또는 동일 (해외 대학)",
  "country": "ISO 2자리 코드 (KR/US/UK/JP/CN/...)",
  "confidence": 0.0~1.0 (이 매핑이 얼마나 확실한가),
  "is_university": true/false (실제 대학교/대학원/college인가, 아니면 어학원·기관 등인가)
}}

규칙:
- 한국 대학명은 항상 한글 정식 명칭 사용 (예: "Dongguk University" → "동국대학교")
- 해외 대학은 원어 그대로 (예: "Stanford University" → "Stanford University")
- 약어 풀어 쓰기 (예: "KAIST" → "한국과학기술원")
- 한+영 병기 표기는 한글 부분 추출 (예: "한국외국어대학교 (Hankuk Univ of Foreign Language)" → "한국외국어대학교")
- "동국 대학교" 같은 띄어쓰기 변형도 정식 표기로
- 어학원·연수기관·고등학교 등 대학이 아니면 is_university=false
- 매우 모호하거나 식별 불가능하면 confidence < 0.7

예시:
입력: "Hankuk University of Foreign Studies"
출력: {{"canonical_name": "한국외국어대학교", "name_en": "Hankuk University of Foreign Studies", "country": "KR", "confidence": 0.99, "is_university": true}}

입력: "USC GOULD"
출력: {{"canonical_name": "USC Gould School of Law", "name_en": "USC Gould School of Law", "country": "US", "confidence": 0.95, "is_university": true}}
"""


def _ask_llm_for_canonical(raw_name: str) -> dict | None:
    """Call Gemini to map raw_name → canonical institution metadata.

    Returns dict with canonical_name/name_en/country/confidence/is_university,
    or None on failure.
    """
    try:
        from data_extraction.services.extraction.gemini import (
            GEMINI_MODEL,
            _get_gemini_client,
        )
        from data_extraction.services.extraction.sanitizers import parse_llm_json
        from google import genai
    except Exception:
        logger.exception("Failed to import Gemini client for institution mapping")
        return None

    client = _get_gemini_client()
    prompt = _LLM_MAPPING_PROMPT.format(raw_name=raw_name)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                max_output_tokens=300,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        result = parse_llm_json(response.text)
        if not isinstance(result, dict) or "canonical_name" not in result:
            logger.warning("LLM returned invalid institution mapping for %r", raw_name)
            return None
        return result
    except Exception:
        logger.exception("Institution LLM mapping failed for %r", raw_name)
        return None


# ===========================================================================
# Resolver — public API
# ===========================================================================


def _register_from_llm(raw_name: str, llm_result: dict) -> str | None:
    """Persist a new UniversityTier from LLM mapping. Returns canonical name."""
    from clients.models import UniversityTier

    canonical_name = (llm_result.get("canonical_name") or "").strip()
    name_en = (llm_result.get("name_en") or "").strip()
    country = (llm_result.get("country") or "KR").strip().upper() or "KR"
    confidence = float(llm_result.get("confidence") or 0.0)
    is_university = bool(llm_result.get("is_university", True))

    if not canonical_name or not is_university or confidence < 0.7:
        return None

    try:
        with transaction.atomic():
            row, created = UniversityTier.objects.get_or_create(
                name=canonical_name,
                country=country,
                defaults={
                    "name_en": name_en,
                    "auto_added": True,
                    "needs_review": True,
                    "aliases": [raw_name] if raw_name != canonical_name else [],
                    "notes": f"LLM mapping confidence={confidence:.2f}",
                },
            )
            if not created:
                # Add raw_name to aliases if missing — strengthens future lookups
                if raw_name and raw_name != row.name and raw_name != row.name_en:
                    aliases = list(row.aliases or [])
                    if raw_name not in aliases:
                        aliases.append(raw_name)
                        row.aliases = aliases
                        row.save(update_fields=["aliases", "updated_at"])
        _invalidate_lookup_index()
        return canonical_name
    except Exception:
        logger.exception("Failed to register UniversityTier from LLM mapping")
        return None


@lru_cache(maxsize=10000)
def _resolve_cached(raw_name: str, *, allow_llm: bool) -> str:
    """Cached resolver — same raw_name returns same canonical without re-querying.

    Cache invalidated when new UniversityTier rows are added.
    """
    if not raw_name:
        return raw_name

    # 1) Master lookup
    canonical = _master_lookup(raw_name)
    if canonical:
        return canonical

    # 2) LLM fallback (optional — disabled in tests for determinism)
    if not allow_llm:
        return raw_name

    llm_result = _ask_llm_for_canonical(raw_name)
    if not llm_result:
        return raw_name

    canonical = _register_from_llm(raw_name, llm_result)
    if canonical:
        return canonical

    return raw_name


def resolve_institution(raw_name: str, *, allow_llm: bool = True) -> str:
    """Resolve a raw institution name to its canonical form.

    Args:
        raw_name: institution name as extracted by LLM (may be 한글/영문/병기/약어).
        allow_llm: if False, skip LLM fallback (lookup only). Useful for tests
            and offline batch processing.

    Returns canonical name from UniversityTier. If no match found and LLM
    didn't return high-confidence mapping, returns raw_name unchanged.
    """
    return _resolve_cached(raw_name, allow_llm=allow_llm)
