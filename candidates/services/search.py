"""Search engine: natural language → structured filters + hybrid search."""

from __future__ import annotations

import logging
from functools import reduce
from operator import or_

from django.db.models import Q, QuerySet

from candidates.models import Candidate, CandidateEmbedding
from common.embedding import get_embedding
from common.llm import call_llm_json

logger = logging.getLogger(__name__)

CATEGORY_NAMES = [
    "Accounting",
    "EHS",
    "Engineer",
    "Finance",
    "HR",
    "Law",
    "Logistics",
    "Marketing",
    "MD",
    "MR",
    "Plant",
    "PR+AD",
    "Procurement",
    "Production",
    "Quality",
    "R&D",
    "Sales",
    "SCM",
    "SI+IT",
    "VMD",
]

SEARCH_SYSTEM_PROMPT = (
    "당신은 헤드헌팅 후보자 검색 시스템입니다.\n"
    "사용자의 자연어 검색 요청을 구조화된 필터 JSON으로 변환합니다.\n\n"
    "사용 가능한 카테고리: " + ", ".join(CATEGORY_NAMES) + "\n\n"
    "규칙:\n"
    "1. 확실하지 않은 필터는 null로 두세요.\n"
    "2. 회사명 필터는 부분 매치입니다 (예: '삼성' → 삼성전자, 삼성SDI 등 포함).\n"
    "3. action은 'new'(새 검색), 'narrow'(현재 결과에서 좁히기), 'broaden'(넓히기) 중 하나.\n"
    "4. ai_message는 사용자에게 보여줄 응답 메시지입니다. 한국어 존대말로 작성하세요.\n"
    "5. JSON만 출력하세요.\n\n"
    "출력 JSON 스키마:\n"
    "{\n"
    '  "filters": {\n'
    '    "category": "string | null",\n'
    '    "min_experience_years": "integer | null",\n'
    '    "max_experience_years": "integer | null",\n'
    '    "companies_include": ["string"] | null,\n'
    '    "education_keyword": "string | null",\n'
    '    "position_keyword": "string | null"\n'
    "  },\n"
    '  "semantic_query": "string (시맨틱 검색용 요약 텍스트)",\n'
    '  "action": "new | narrow | broaden",\n'
    '  "ai_message": "string (사용자에게 보여줄 메시지)"\n'
    "}"
)


def parse_search_query(user_text: str, current_filters: dict) -> dict:
    """Convert natural language query to structured search filters via LLM."""
    prompt_parts = []
    if current_filters:
        prompt_parts.append(f"현재 적용된 필터: {current_filters}")
    prompt_parts.append(f"사용자 요청: {user_text}")
    prompt = "\n".join(prompt_parts)

    try:
        result = call_llm_json(
            prompt, system=SEARCH_SYSTEM_PROMPT, timeout=120, max_tokens=500
        )
        if not isinstance(result, dict) or "filters" not in result:
            return _fallback_result(user_text)
        result.setdefault("action", "new")
        result.setdefault("ai_message", "검색 결과를 확인해주세요.")
        result.setdefault("semantic_query", user_text)
        return result
    except Exception:
        logger.exception("LLM search query parsing failed")
        return _fallback_result(user_text)


def _fallback_result(user_text: str) -> dict:
    return {
        "filters": {},
        "semantic_query": user_text,
        "action": "new",
        "ai_message": "정확한 필터 대신 유사 검색으로 찾았습니다.",
    }


def execute_structured_search(filters: dict) -> QuerySet[Candidate]:
    """Apply structured filters to Candidate queryset."""
    qs = Candidate.objects.select_related("primary_category").prefetch_related(
        "categories"
    )

    category = filters.get("category")
    if category:
        qs = qs.filter(categories__name=category)

    min_exp = filters.get("min_experience_years")
    if min_exp is not None:
        qs = qs.filter(total_experience_years__gte=min_exp)

    max_exp = filters.get("max_experience_years")
    if max_exp is not None:
        qs = qs.filter(total_experience_years__lte=max_exp)

    companies = filters.get("companies_include")
    if companies:
        q_list = [Q(current_company__icontains=c) for c in companies]
        career_q = [Q(careers__company__icontains=c) for c in companies]
        qs = qs.filter(reduce(or_, q_list + career_q)).distinct()

    edu_kw = filters.get("education_keyword")
    if edu_kw:
        qs = qs.filter(
            Q(educations__institution__icontains=edu_kw)
            | Q(educations__major__icontains=edu_kw)
        ).distinct()

    position_kw = filters.get("position_keyword")
    if position_kw:
        qs = qs.filter(
            Q(current_position__icontains=position_kw)
            | Q(careers__position__icontains=position_kw)
        ).distinct()

    return qs


def hybrid_search(
    filters: dict, semantic_query: str | None = None, limit: int = 50
) -> list[Candidate]:
    """Hybrid search: structured filters + semantic ranking."""
    qs = execute_structured_search(filters)

    if semantic_query:
        query_vec = get_embedding(semantic_query)
        if query_vec:
            candidate_ids = set(qs.values_list("id", flat=True))
            if candidate_ids:
                embeddings = (
                    CandidateEmbedding.objects.filter(candidate_id__in=candidate_ids)
                    .select_related("candidate", "candidate__primary_category")
                    .order_by(CandidateEmbedding.cosine_distance_expression(query_vec))[
                        :limit
                    ]
                )
                ranked = [e.candidate for e in embeddings]
                ranked_ids = {c.id for c in ranked}
                unranked = qs.exclude(id__in=ranked_ids)[:limit]
                return ranked + list(unranked)
            return []

    return list(qs.order_by("-updated_at")[:limit])
