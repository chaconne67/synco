"""Search engine: natural language -> LLM-generated structured filters -> ORM."""

from __future__ import annotations

import json
import logging
from collections import Counter

from django.db.models import (
    Case,
    F,
    IntegerField,
    Min,
    Prefetch,
    Q,
    QuerySet,
    Value,
    When,
)

from common.llm import call_llm

logger = logging.getLogger(__name__)

FILTER_SPEC_TEMPLATE = {
    "category": None,
    "name_keywords": [],
    "company_keywords": [],
    "school_keywords": [],
    "school_groups": [],
    "major_keywords": [],
    "certification_keywords": [],
    "language_keywords": [],
    "position_keywords": [],
    "skill_keywords": [],
    "keyword": None,
    "gender": None,
    "min_experience_years": None,
    "max_experience_years": None,
    "min_rank": None,
    "max_rank": None,
    "birth_year_from": None,
    "birth_year_to": None,
    "is_abroad_education": None,
    "recommendation_status": [],
    "sort_by": None,
    "limit": None,
}

# 정렬 키 → ORM order_by 식. NULL은 항상 마지막으로 밀어서 의미있는 결과부터 노출.
# birth_year가 높을수록 어림(최근 출생).
# university_rank_asc는 annotation 기반이라 별도 분기 처리.
VALID_SORT_BY: dict[str, object] = {
    "age_asc": F("birth_year").desc(nulls_last=True),  # 나이 어린 순
    "age_desc": F("birth_year").asc(nulls_last=True),  # 나이 많은 순
    "experience_desc": F("total_experience_years").desc(nulls_last=True),
    "experience_asc": F("total_experience_years").asc(nulls_last=True),
    "updated_desc": F("updated_at").desc(nulls_last=True),
}
VALID_SORT_BY_KEYS: frozenset[str] = frozenset(VALID_SORT_BY) | {"university_rank_asc"}

# 한국 기업 공식 직급 체계 (오름차순). 팀장·임원·본부장 같은 역할명은 제외.
RANK_HIERARCHY: list[str] = [
    "인턴",
    "사원",
    "주임",
    "대리",
    "과장",
    "차장",
    "부장",
    "이사",
    "상무",
    "전무",
    "부사장",
    "사장",
]

_RANK_INDEX: dict[str, int] = {name: idx for idx, name in enumerate(RANK_HIERARCHY)}

# 대학 그룹명 → 검색 토큰 리스트 (canonical 학교명이 아닌 icontains 매칭용 토큰)
UNIVERSITY_GROUPS: dict[str, list[str]] = {
    "SKY": ["서울대", "연세대", "고려대"],
    "서성한": ["서강대", "��균관대", "한양대"],
    "중경외시": ["중앙대", "경희대", "한국외대", "��울시립대"],
    "건동홍숙이": ["건국대", "동국대", "홍익��", "숙명여대", "이화여대"],
    "국숭세단": ["국민대", "숭실대", "세종대", "단국대"],
    "과기특": [
        "KAIST",
        "한국과학기술원",
        "POSTECH",
        "포항공과대",
        "UNIST",
        "GIST",
        "DGIST",
    ],
    "지거국": [
        "부산대",
        "경북대",
        "전남대",
        "전북대",
        "충남대",
        "충북대",
        "강원대",
        "제주대",
    ],
    "이공계명문": [
        "KAIST",
        "한국과학기술원",
        "POSTECH",
        "포항공과대",
        "서울대",
        "UNIST",
        "GIST",
    ],
}

# 복합 그룹 (기본 그룹 조합)
UNIVERSITY_GROUPS["명문대"] = sorted(
    set(
        UNIVERSITY_GROUPS["SKY"]
        + UNIVERSITY_GROUPS["서성한"]
        + UNIVERSITY_GROUPS["과기특"]
    )
)
UNIVERSITY_GROUPS["인서울"] = sorted(
    set(
        school
        for g in ["SKY", "서성한", "중경외시", "건동홍숙이", "국숭세단"]
        for school in UNIVERSITY_GROUPS[g]
    )
    | {"서울과기대", "서울과학기술대", "상명대", "광운대", "명지대"}
)

# 그룹명 정규화: LLM이 변형된 형태로 출력할 경우 대응
_GROUP_NAME_ALIASES: dict[str, str] = {
    "이공계명문대": "이공계명문",
    "명문대학": "명문대",
}


def _resolve_group_name(raw: str) -> str:
    """그룹명 정규화: strip, 대소문자, 공백 제거, alias 순으로 처리."""
    name = raw.strip()
    # 1) 대소문자 통일 (SKY, sky, Sky → SKY)
    upper = name.upper()
    if upper in UNIVERSITY_GROUPS:
        return upper
    # 2) 원본 매칭
    if name in UNIVERSITY_GROUPS:
        return name
    # 3) 공백 제거 후 재시도
    no_space = name.replace(" ", "")
    if no_space in UNIVERSITY_GROUPS:
        return no_space
    # 4) alias 매칭 (원본 + 공백 제거 모두 시도)
    if name in _GROUP_NAME_ALIASES:
        return _GROUP_NAME_ALIASES[name]
    if no_space in _GROUP_NAME_ALIASES:
        return _GROUP_NAME_ALIASES[no_space]
    return name  # 폴백: 원본 그대로 반환


FILTER_SCHEMA_TEMPLATE = """
후보자 검색 필터 스키마:
{{
  "category": "string | null",
  "name_keywords": ["string"],
  "company_keywords": ["string"],
  "school_keywords": ["string"],
  "school_groups": ["string"],
  "major_keywords": ["string"],
  "certification_keywords": ["string"],
  "language_keywords": ["string"],
  "position_keywords": ["string"],
  "skill_keywords": ["string"],
  "keyword": "string | null",
  "gender": "string | null",
  "min_experience_years": "integer | null",
  "max_experience_years": "integer | null",
  "min_rank": "string | null",
  "max_rank": "string | null",
  "birth_year_from": "integer | null",
  "birth_year_to": "integer | null",
  "is_abroad_education": "boolean | null",
  "recommendation_status": ["string"],
  "sort_by": "string | null",
  "limit": "integer | null"
}}

실제 값 참고:
- category: {category_values}
- gender: {gender_values}
- degree 상위값: {degree_values}
- position 상위값: {position_values}
- language 상위값: {language_values}
- skill_keywords: 기술 스택 키워드 (영문 공식명으로 변환). 예: 사용자가 '파이썬'이라고 하면 'Python'으로 변환
- recommendation_status: 헤드헌터가 인터뷰 후 수동 판정한 추천 상태 (recommended=채용 추천 적합, not_recommended=위조/부적합 의심, on_hold=추가 검토 필요, pending=미판정). {recommendation_values} 중 해당 값 리스트. "추천만" → ["recommended"]. "비추천 제외" → ["recommended", "on_hold", "pending"]. 빈 리스트 = 전체.
- school_groups: 대학 그룹명. 사용 가능: SKY(서울대/연세대/고려대), 서성한(서강대/성균관대/한양대), 중경외시(중앙대/경희대/한국외대/서울시립대), 건동홍숙이(건국대/동국대/홍익대/숙명여대/이화여대), 국숭세단(국민대/숭실대/세종대/단국대), 과기특(KAIST/POSTECH/UNIST/GIST/DGIST), 지거국(부산대~제주대), 인서울(서울 주요 대학 전체), 명문대(SKY+서성한+과기특), 이공계명문(KAIST/POSTECH/서울대/UNIST/GIST). 개별 학교명은 school_keywords 사용.
- min_rank / max_rank: 직급 범위. 직급 계층(오름차순): 인턴 < 사원 < 주임 < 대리 < 과장 < 차장 < 부장 < 이사 < 상무 < 전무 < 부사장 < 사장. "과장 이상"/"과장급 이상" → min_rank="과장". "부장 이하" → max_rank="부장". "과장부터 부장까지" → min_rank="과장", max_rank="부장". 팀장/임원/본부장/실장 같은 역할명은 직급이 아니므로 position_keywords에 넣으세요.
- sort_by: 정렬 기준. 사용 가능: "age_asc"(나이 어린 순), "age_desc"(나이 많은 순), "experience_desc"(경력 많은 순), "experience_asc"(경력 적은 순), "university_rank_asc"(대학 랭킹 높은 순 — 서울대·KAIST 우선), "updated_desc"(최신 등록 순, 기본값). 사용자가 정렬을 언급하지 않으면 null.
- limit: 결과 최대 인원수. 1~100. "상위 N명"/"N명만"/"N명 뽑아줘"처럼 결과 수 지정 시 해당 값, 아니면 null.
"""


def _top_values(values, limit: int = 8) -> str:
    counts = Counter(v for v in values if v)
    return ", ".join(f"'{val}'" for val, _ in counts.most_common(limit))


def _build_filter_schema() -> str:
    from candidates.models import Candidate, Career, Category, Education, LanguageSkill

    rec_values = [c.value for c in Candidate.RecommendationStatus]
    return FILTER_SCHEMA_TEMPLATE.format(
        category_values=", ".join(
            c.name for c in Category.objects.all().order_by("name")
        ),
        gender_values=_top_values(Candidate.objects.values_list("gender", flat=True)),
        degree_values=_top_values(Education.objects.values_list("degree", flat=True)),
        position_values=_top_values(Career.objects.values_list("position", flat=True)),
        language_values=_top_values(
            LanguageSkill.objects.values_list("language", flat=True)
        ),
        recommendation_values=str(rec_values),
    )


_filter_schema_cache: str | None = None


def _get_filter_schema() -> str:
    global _filter_schema_cache
    if _filter_schema_cache is None:
        _filter_schema_cache = _build_filter_schema()
    return _filter_schema_cache


_SEARCH_SYSTEM_PROMPT_TEMPLATE = """당신은 헤드헌팅 후보자 검색 필터 생성기입니다.

## 역할
1. 사용자의 자연어 요청이 헤드헌팅 업무(후보자 검색, 인재 추천, 채용 관련)인지 판단합니다.
2. 헤드헌팅 업무이면 아래 필터 스키마에 맞는 JSON을 생성합니다.
3. 헤드헌팅 업무가 아니면 거절합니다.
4. 이전 필터가 주어지면, 새 요청을 반영한 최종 필터 상태를 완성해서 반환합니다.

## 헤드헌팅 관련 업무 예시
- 후보자 검색/추천 (경력, 학력, 회사, 직무, 나이, 성별 등)
- 현재 결과 좁히기 ("거기서 삼성 출신만", "10년 이상만")
- 인재풀 조회, 필터링

## 헤드헌팅 업무가 아닌 예시
- 일반 대화, 인사, 잡담
- 날씨, 뉴스, 일정
- 프로그래밍, 번역 등 다른 업무

## 필터 스키마
{filter_schema}

## 출력 형식 (JSON만 출력)

헤드헌팅 관련 요청인 경우:
```json
{{
  "is_valid": true,
  "filters": {{
    "category": null,
    "name_keywords": [],
    "company_keywords": [],
    "school_keywords": [],
    "school_groups": [],
    "major_keywords": [],
    "certification_keywords": [],
    "language_keywords": [],
    "position_keywords": [],
    "skill_keywords": [],
    "keyword": null,
    "gender": null,
    "min_experience_years": null,
    "max_experience_years": null,
    "min_rank": null,
    "max_rank": null,
    "birth_year_from": null,
    "birth_year_to": null,
    "is_abroad_education": null,
    "recommendation_status": [],
    "sort_by": null,
    "limit": null
  }},
  "ai_message": "..."
}}
```

헤드헌팅 관련이 아닌 경우:
```json
{{"is_valid": false, "filters": null, "ai_message": "죄송합니다. 저는 후보자 검색 전용 AI입니다."}}
```

## 규칙
1. JSON 외 다른 텍스트를 출력하지 마세요.
2. 사용자가 새 검색을 명확히 시작하면 이전 필터를 버리고 새 최종 필터를 반환하세요.
3. 사용자가 "거기서", "그중", "추가로", "좁혀서"처럼 말하면 이전 필터를 유지한 채 조건을 더하세요.
4. 문자열 배열은 중복 없이 간결한 키워드만 넣으세요.
5. 사용자가 말하지 않은 정보를 추정해서 필터에 넣지 마세요.
6. 올해는 2026년입니다. "나이 50"은 출생연도 범위로 바꾸세요.
7. 학교 소재지, 업종 분류처럼 DB에 없는 정보는 필터로 만들지 말고 ai_message에 한계를 짧게 설명하세요.
8. 숫자가 고유명사의 일부일 수 있습니다. "1급소방안전관리자", "3PL Team", "新HSK 6급" 같은 표현은 하나의 키워드로 유지하세요.
9. 빈 필터는 null 또는 빈 배열로 유지하세요.
10. 사용자가 대학 그룹명(SKY, 인서울, 서성한, 과기특 등)을 사용하면 school_groups에 넣으세요. 개별 학교명(서울대, KAIST 등)은 school_keywords에 넣으세요.
11. "명문대", "상위권 대학", "이공계 명문" 등 그룹 의미의 표현은 가장 가까운 school_groups 값으로 변환하세요.
12. 그룹명과 개별 학교를 함께 언급하면("SKY나 KAIST", "인서울이나 부산대") 모두 school_groups로 통합하세요. 개별 학교는 가장 가까운 그룹에 포함시키세요(예: KAIST → 과기특). school_groups와 school_keywords를 동시에 사용하지 마세요.
13. "X급 이상"/"X 이상"/"X 이하"/"X부터 Y까지" 같은 직급 범위 표현은 min_rank/max_rank에 넣으세요. position_keywords에 여러 직급을 열거하면 AND로 묶여 결과가 0이 됩니다. 단일 직급 한정("과장만") 역시 min_rank=max_rank="과장"으로 넣는 편이 안전합니다. 팀장/임원/본부장 같은 역할명만 position_keywords에 넣으세요.
14. "나이 어린 순"/"어린 순"/"영 순" → sort_by="age_asc". "나이 많은 순"/"연배 순" → sort_by="age_desc". "경력 많은 순"/"베테랑 순" → sort_by="experience_desc". "경력 짧은 순"/"주니어 순" → sort_by="experience_asc". "대학 랭킹순"/"명문대 순"/"학벌순"/"학교 좋은 순" → sort_by="university_rank_asc". "상위 N명"/"N명 뽑아줘"/"N명만" → limit=N. 정렬·제한은 필터 조건이 아니라 결과 표시 방식이므로 "거기서 5명만" 같은 좁히기 요청에도 이전 필터를 유지한 채 limit만 추가하세요.
15. certification_keywords는 OR로 결합됩니다 — 같은 자격증의 다양한 표기를 모두 나열하면 누락이 줄어듭니다. 다만 공인회계사처럼 substring 충돌 위험이 있는 경우 모호한 공통 표기("공인회계사")는 절대 넣지 말고 구분된 정확 표기만 사용하세요. "한국 CPA"/"한국 공인회계사"/"KICPA" → ["KICPA", "한국공인회계사", "한국 공인회계사"]. "미국 CPA"/"AICPA"/"USCPA" → ["AICPA", "USCPA", "미국공인회계사", "미국 공인회계사"]. 그냥 "CPA"만 말하면 양쪽 모두 합쳐서 나열하세요.
16. ai_message에는 최종 검색 조건을 한국어로 짧게 요약하세요."""

_search_prompt_cache: str | None = None


def _get_search_prompt() -> str:
    global _search_prompt_cache
    if _search_prompt_cache is None:
        _search_prompt_cache = _SEARCH_SYSTEM_PROMPT_TEMPLATE.format(
            filter_schema=_get_filter_schema()
        )
    return _search_prompt_cache


def _extract_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _clean_text_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _clean_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def normalize_filter_spec(filters: dict | None) -> dict:
    normalized = dict(FILTER_SPEC_TEMPLATE)
    if not isinstance(filters, dict):
        return normalized

    normalized["category"] = (
        filters.get("category").strip()
        if isinstance(filters.get("category"), str) and filters.get("category").strip()
        else None
    )
    normalized["keyword"] = (
        filters.get("keyword").strip()
        if isinstance(filters.get("keyword"), str) and filters.get("keyword").strip()
        else None
    )
    normalized["gender"] = (
        filters.get("gender").strip()
        if isinstance(filters.get("gender"), str) and filters.get("gender").strip()
        else None
    )
    normalized["name_keywords"] = _clean_text_list(filters.get("name_keywords"))
    normalized["company_keywords"] = _clean_text_list(filters.get("company_keywords"))
    normalized["school_keywords"] = _clean_text_list(filters.get("school_keywords"))
    normalized["school_groups"] = _clean_text_list(filters.get("school_groups"))
    normalized["major_keywords"] = _clean_text_list(filters.get("major_keywords"))
    normalized["certification_keywords"] = _clean_text_list(
        filters.get("certification_keywords")
    )
    normalized["language_keywords"] = _clean_text_list(filters.get("language_keywords"))
    normalized["position_keywords"] = _clean_text_list(filters.get("position_keywords"))
    if "skill_keywords" in filters:
        val = filters["skill_keywords"]
        if isinstance(val, str):
            normalized["skill_keywords"] = [val]
        elif isinstance(val, list):
            normalized["skill_keywords"] = _clean_text_list(val)
        else:
            normalized["skill_keywords"] = []
    normalized["min_experience_years"] = _clean_int(filters.get("min_experience_years"))
    normalized["max_experience_years"] = _clean_int(filters.get("max_experience_years"))

    raw_min_rank = filters.get("min_rank")
    raw_max_rank = filters.get("max_rank")
    normalized["min_rank"] = (
        raw_min_rank.strip()
        if isinstance(raw_min_rank, str) and raw_min_rank.strip() in _RANK_INDEX
        else None
    )
    normalized["max_rank"] = (
        raw_max_rank.strip()
        if isinstance(raw_max_rank, str) and raw_max_rank.strip() in _RANK_INDEX
        else None
    )

    normalized["birth_year_from"] = _clean_int(filters.get("birth_year_from"))
    normalized["birth_year_to"] = _clean_int(filters.get("birth_year_to"))
    normalized["is_abroad_education"] = _clean_bool(filters.get("is_abroad_education"))

    # recommendation_status: list of valid values
    from candidates.models import Candidate as _Cand

    valid_rec = {c.value for c in _Cand.RecommendationStatus}
    raw_rec = filters.get("recommendation_status", [])
    if isinstance(raw_rec, str):
        raw_rec = [raw_rec]
    normalized["recommendation_status"] = [v for v in raw_rec if v in valid_rec]

    raw_sort = filters.get("sort_by")
    normalized["sort_by"] = (
        raw_sort
        if isinstance(raw_sort, str) and raw_sort in VALID_SORT_BY_KEYS
        else None
    )
    raw_limit = _clean_int(filters.get("limit"))
    normalized["limit"] = (
        raw_limit if raw_limit is not None and 1 <= raw_limit <= 100 else None
    )

    return normalized


def has_active_filters(filters: dict | None) -> bool:
    normalized = normalize_filter_spec(filters)
    for key, value in normalized.items():
        if isinstance(value, list):
            if value:
                return True
            continue
        if value is not None:
            return True
    return False


def _apply_keyword_filters(
    qs: QuerySet,
    field_groups: list[tuple[str, ...]],
    keywords: list[str],
    combine: str = "and",
) -> QuerySet:
    """combine="and": 키워드마다 별도 filter(AND 결합). combine="or": 키워드 전체 OR 결합."""
    if combine == "or":
        outer = Q()
        for keyword in keywords:
            for group in field_groups:
                for field in group:
                    outer |= Q(**{f"{field}__icontains": keyword})
        if outer:
            qs = qs.filter(outer)
        return qs
    for keyword in keywords:
        group_query = Q()
        for group in field_groups:
            field_query = Q()
            for field in group:
                field_query |= Q(**{f"{field}__icontains": keyword})
            group_query |= field_query
        qs = qs.filter(group_query)
    return qs


def build_search_queryset(filters: dict | None) -> QuerySet:
    from candidates.models import Candidate, DiscrepancyReport

    normalized = normalize_filter_spec(filters)
    qs = Candidate.objects.select_related("primary_category").prefetch_related(
        "educations",
        "careers",
        "categories",
        "certifications",
        "language_skills",
        Prefetch(
            "discrepancy_reports",
            queryset=DiscrepancyReport.objects.filter(
                report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY
            ).order_by("-created_at"),
            to_attr="prefetched_self_consistency_reports",
        ),
    )

    if normalized["category"]:
        qs = qs.filter(categories__name__iexact=normalized["category"])

    if normalized["gender"]:
        qs = qs.filter(gender__iexact=normalized["gender"])

    if normalized["min_experience_years"] is not None:
        qs = qs.filter(total_experience_years__gte=normalized["min_experience_years"])

    if normalized["max_experience_years"] is not None:
        qs = qs.filter(total_experience_years__lte=normalized["max_experience_years"])

    if normalized["birth_year_from"] is not None:
        qs = qs.filter(birth_year__gte=normalized["birth_year_from"])

    if normalized["birth_year_to"] is not None:
        qs = qs.filter(birth_year__lte=normalized["birth_year_to"])

    if normalized["is_abroad_education"] is not None:
        qs = qs.filter(educations__is_abroad=normalized["is_abroad_education"])

    if normalized["recommendation_status"]:
        qs = qs.filter(recommendation_status__in=normalized["recommendation_status"])

    qs = _apply_keyword_filters(
        qs,
        [("name", "name_en")],
        normalized["name_keywords"],
    )
    qs = _apply_keyword_filters(
        qs,
        [("current_company",), ("careers__company", "careers__company_en")],
        normalized["company_keywords"],
    )
    qs = _apply_keyword_filters(
        qs,
        [("educations__institution",)],
        normalized["school_keywords"],
    )
    # school_groups: 그룹명을 개별 학교 토큰으로 확장하여 OR 필터 적용
    school_groups = normalized.get("school_groups") or []
    if school_groups:
        group_q = Q()
        seen: set[str] = set()
        for raw_name in school_groups:
            group_name = _resolve_group_name(raw_name)
            schools = UNIVERSITY_GROUPS.get(group_name, [])
            if not schools:
                group_q |= Q(educations__institution__icontains=group_name)
            else:
                for school in schools:
                    if school not in seen:
                        group_q |= Q(educations__institution__icontains=school)
                        seen.add(school)
        if group_q:
            qs = qs.filter(group_q)
    qs = _apply_keyword_filters(
        qs,
        [("educations__major",)],
        normalized["major_keywords"],
    )
    qs = _apply_keyword_filters(
        qs,
        [("certifications__name", "certifications__issuer")],
        normalized["certification_keywords"],
        combine="or",
    )
    qs = _apply_keyword_filters(
        qs,
        [
            (
                "language_skills__language",
                "language_skills__test_name",
                "language_skills__level",
            )
        ],
        normalized["language_keywords"],
    )
    qs = _apply_keyword_filters(
        qs,
        [("current_position",), ("careers__position", "careers__department")],
        normalized["position_keywords"],
    )

    # 직급 범위 필터: min_rank/max_rank → 직급 계층을 OR icontains로 확장
    min_rank = normalized.get("min_rank")
    max_rank = normalized.get("max_rank")
    if min_rank or max_rank:
        low = _RANK_INDEX[min_rank] if min_rank else 0
        high = _RANK_INDEX[max_rank] if max_rank else len(RANK_HIERARCHY) - 1
        if low <= high:
            rank_q = Q()
            for rank in RANK_HIERARCHY[low : high + 1]:
                rank_q |= Q(current_position__icontains=rank)
                rank_q |= Q(careers__position__icontains=rank)
            qs = qs.filter(rank_q)

    skill_keywords = normalized.get("skill_keywords") or []
    if skill_keywords:
        for kw in skill_keywords:
            qs = qs.filter(
                Q(skills__contains=[kw]) | Q(skills__contains=[{"name": kw}])
            )

    if normalized["keyword"]:
        kw = normalized["keyword"]
        qs = qs.filter(
            Q(name__icontains=kw)
            | Q(name_en__icontains=kw)
            | Q(current_company__icontains=kw)
            | Q(current_position__icontains=kw)
            | Q(summary__icontains=kw)
            | Q(careers__company__icontains=kw)
            | Q(careers__position__icontains=kw)
            | Q(careers__duties__icontains=kw)
            | Q(careers__achievements__icontains=kw)
            | Q(educations__institution__icontains=kw)
            | Q(educations__major__icontains=kw)
            | Q(certifications__name__icontains=kw)
            | Q(skills__icontains=kw)
        )

    sort_by = normalized.get("sort_by")
    if sort_by == "university_rank_asc":
        # 후보자 educations.institution을 UniversityTier.name과 icontains 매칭해
        # 최상위(=ranking 최소) 대학 번호로 정렬. 매칭 실패/unranked는 9999로 뒤로.
        univ_case = _build_university_rank_case()
        if univ_case is not None:
            qs = qs.annotate(_univ_rank=Min(univ_case))
            return qs.order_by("_univ_rank", F("updated_at").desc(nulls_last=True))

    sort_key = VALID_SORT_BY.get(sort_by or "", F("updated_at").desc(nulls_last=True))
    return qs.distinct().order_by(sort_key)


_university_rank_cache: list[dict] | None = None


def _load_ranked_universities() -> list[dict]:
    global _university_rank_cache
    if _university_rank_cache is None:
        from clients.models import UniversityTier

        _university_rank_cache = list(
            UniversityTier.objects.exclude(ranking__isnull=True)
            .order_by("ranking")
            .values("name", "ranking")
        )
    return _university_rank_cache


def _build_university_rank_case() -> Case | None:
    """icontains Case 식: educations.institution → UniversityTier.ranking."""
    tiers = _load_ranked_universities()
    if not tiers:
        return None
    cases = [
        When(educations__institution__icontains=t["name"], then=Value(t["ranking"]))
        for t in tiers
    ]
    return Case(*cases, default=Value(9999), output_field=IntegerField())


def parse_and_search(user_text: str, previous_filters: dict | None = None) -> dict:
    """Natural language -> LLM filters -> ORM results."""
    normalized_previous = normalize_filter_spec(previous_filters)
    prompt_parts = [
        "이전 필터(JSON):",
        json.dumps(normalized_previous, ensure_ascii=False),
        f"사용자 요청: {user_text}",
    ]
    prompt = "\n".join(prompt_parts)

    try:
        raw = call_llm(prompt, system=_get_search_prompt(), timeout=60, max_tokens=900)
        parsed = _extract_json(raw)
    except Exception:
        logger.exception("LLM filter generation failed")
        return {
            "candidates": [],
            "filters": normalized_previous,
            "ai_message": "검색 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
            "is_valid": True,
            "result_count": 0,
        }

    if not parsed.get("is_valid"):
        return {
            "candidates": [],
            "filters": normalized_previous,
            "ai_message": parsed.get(
                "ai_message",
                "죄송합니다. 저는 후보자 검색 전용 AI입니다.",
            ),
            "is_valid": False,
            "result_count": 0,
        }

    filters = normalize_filter_spec(parsed.get("filters"))
    qs = build_search_queryset(filters)
    limit = filters.get("limit") or 100
    results = list(qs.values("id", "name")[:limit])
    total_count = (
        min(qs.count(), filters.get("limit")) if filters.get("limit") else qs.count()
    )
    ai_message = parsed.get("ai_message", f"{total_count}명을 찾았습니다.")

    return {
        "candidates": results,
        "filters": filters,
        "ai_message": ai_message,
        "is_valid": True,
        "result_count": total_count,
    }
