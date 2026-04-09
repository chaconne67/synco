import json
from unittest.mock import patch

import pytest

from candidates.models import Candidate, Career, Category, Certification, Education
from candidates.services.search import (
    UNIVERSITY_GROUPS,
    _resolve_group_name,
    build_search_queryset,
    has_active_filters,
    normalize_filter_spec,
    parse_and_search,
)


@pytest.fixture
def accounting_category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def hr_category(db):
    return Category.objects.create(name="HR", name_ko="인사")


@pytest.mark.django_db
@patch("candidates.services.search.call_llm")
def test_parse_and_search_returns_structured_filter_results(
    mock_llm, accounting_category, hr_category
):
    matching = Candidate.objects.create(
        name="김회계",
        current_company="삼성전자",
        total_experience_years=12,
        primary_category=accounting_category,
    )
    matching.categories.add(accounting_category)
    Career.objects.create(candidate=matching, company="삼성전자", position="과장")
    Education.objects.create(
        candidate=matching, institution="서울대학교", major="경영학"
    )
    Certification.objects.create(candidate=matching, name="KICPA")

    non_matching = Candidate.objects.create(
        name="박인사",
        current_company="네이버",
        total_experience_years=7,
        primary_category=hr_category,
    )
    non_matching.categories.add(hr_category)

    mock_llm.return_value = json.dumps(
        {
            "is_valid": True,
            "filters": {
                "category": "Accounting",
                "company_keywords": ["삼성"],
                "school_keywords": ["서울대학교"],
                "min_experience_years": 10,
            },
            "ai_message": "회계 카테고리에서 삼성 경력, 서울대, 10년 이상 후보자를 찾았습니다.",
        },
        ensure_ascii=False,
    )

    result = parse_and_search("회계 쪽에서 삼성 경력 있고 서울대 나온 10년 이상")

    assert result["is_valid"] is True
    assert result["result_count"] == 1
    assert result["filters"]["category"] == "Accounting"
    assert result["filters"]["company_keywords"] == ["삼성"]
    assert result["candidates"][0]["name"] == "김회계"


@pytest.mark.django_db
@patch("candidates.services.search.call_llm")
def test_parse_and_search_rejects_non_search_request(mock_llm):
    mock_llm.return_value = json.dumps(
        {
            "is_valid": False,
            "filters": None,
            "ai_message": "죄송합니다. 저는 후보자 검색 전용 AI입니다.",
        },
        ensure_ascii=False,
    )

    result = parse_and_search("오늘 날씨 어때?")

    assert result["is_valid"] is False
    assert result["result_count"] == 0
    assert "후보자 검색 전용" in result["ai_message"]


def test_has_active_filters_detects_real_conditions():
    assert has_active_filters({}) is False
    assert has_active_filters({"category": None, "company_keywords": []}) is False
    assert has_active_filters({"company_keywords": ["삼성"]}) is True


# --- University group search tests ---


def test_university_groups_constant_integrity():
    """All group values are non-empty; compound groups contain base group schools."""
    for group_name, schools in UNIVERSITY_GROUPS.items():
        assert len(schools) > 0, f"{group_name} group is empty"

    # 인서울은 SKY를 포함해야 함
    inseoul = set(UNIVERSITY_GROUPS["인서울"])
    for school in UNIVERSITY_GROUPS["SKY"]:
        assert school in inseoul, f"인서울 should contain SKY school {school}"

    # 명문대 = SKY + 서성한 + 과기특
    myungmun = set(UNIVERSITY_GROUPS["명문대"])
    for g in ["SKY", "서성한", "과기특"]:
        for school in UNIVERSITY_GROUPS[g]:
            assert school in myungmun, f"명문대 should contain {g} school {school}"


@pytest.mark.django_db
def test_build_search_queryset_school_groups_sky():
    """SKY group: returns SNU/Yonsei/Korea only, excludes Hanyang."""
    sky_candidates = []
    for inst in ["서울대학교", "연세대학교", "고려대학교"]:
        c = Candidate.objects.create(name=f"test_{inst}")
        Education.objects.create(candidate=c, institution=inst)
        sky_candidates.append(c)

    non_sky = Candidate.objects.create(name="test_한양대")
    Education.objects.create(candidate=non_sky, institution="한양대학교")

    qs = build_search_queryset({"school_groups": ["SKY"]})
    result_ids = set(qs.values_list("id", flat=True))

    for c in sky_candidates:
        assert c.id in result_ids, f"{c.name} should be in SKY results"
    assert non_sky.id not in result_ids


@pytest.mark.django_db
def test_build_search_queryset_school_groups_or_across_groups():
    """여러 그룹 지정 시 OR로 합산."""
    c_snu = Candidate.objects.create(name="test_서울대")
    Education.objects.create(candidate=c_snu, institution="서울대학교")

    c_kaist = Candidate.objects.create(name="test_KAIST")
    Education.objects.create(candidate=c_kaist, institution="KAIST")

    qs = build_search_queryset({"school_groups": ["SKY", "과기특"]})
    result_ids = set(qs.values_list("id", flat=True))

    assert c_snu.id in result_ids
    assert c_kaist.id in result_ids


@pytest.mark.django_db
def test_school_groups_combined_with_other_filters():
    """school_groups + company_keywords 조합: SKY + 삼성만 반환."""
    c_sky_samsung = Candidate.objects.create(name="test_sky_samsung")
    Education.objects.create(candidate=c_sky_samsung, institution="서울대학교")
    Career.objects.create(candidate=c_sky_samsung, company="삼성전자")

    c_sky_naver = Candidate.objects.create(name="test_sky_naver")
    Education.objects.create(candidate=c_sky_naver, institution="연세대학교")
    Career.objects.create(candidate=c_sky_naver, company="네이버")

    qs = build_search_queryset(
        {
            "school_groups": ["SKY"],
            "company_keywords": ["삼성"],
        }
    )
    result_ids = set(qs.values_list("id", flat=True))

    assert c_sky_samsung.id in result_ids
    assert c_sky_naver.id not in result_ids


def test_normalize_filter_spec_school_groups():
    """school_groups 정규화: 빈 값, None, 비문자열 제거."""
    result = normalize_filter_spec({"school_groups": ["SKY", "", "  인서울  ", 123]})
    assert result["school_groups"] == ["SKY", "인서울"]

    assert normalize_filter_spec({})["school_groups"] == []
    assert normalize_filter_spec(None)["school_groups"] == []


def test_has_active_filters_school_groups():
    assert has_active_filters({"school_groups": ["SKY"]}) is True
    assert has_active_filters({"school_groups": []}) is False


@pytest.mark.django_db
@patch("candidates.services.search.call_llm")
def test_parse_and_search_with_school_groups(mock_llm):
    """Integration: LLM returns school_groups, candidates are correctly filtered."""
    c = Candidate.objects.create(name="test_sky_integration")
    Education.objects.create(candidate=c, institution="고려대학교")

    mock_llm.return_value = json.dumps(
        {
            "is_valid": True,
            "filters": {"school_groups": ["SKY"]},
            "ai_message": "SKY 출신 후보자를 찾았습니다.",
        },
        ensure_ascii=False,
    )

    result = parse_and_search("SKY 출신 찾아줘")
    assert result["is_valid"] is True
    assert result["result_count"] >= 1
    assert result["filters"]["school_groups"] == ["SKY"]


@pytest.mark.django_db
def test_school_groups_search_variant_postech():
    """POSTECH variants: both Korean and English forms match via search tokens."""
    c_korean = Candidate.objects.create(name="test_포항공과대학교")
    Education.objects.create(candidate=c_korean, institution="포항공과대학교")

    c_english = Candidate.objects.create(name="test_POSTECH")
    Education.objects.create(candidate=c_english, institution="POSTECH")

    qs = build_search_queryset({"school_groups": ["과기특"]})
    result_ids = set(qs.values_list("id", flat=True))

    assert c_korean.id in result_ids, "포항공과대학교 should match via 포항공과대 token"
    assert c_english.id in result_ids, "POSTECH should match via POSTECH token"


@pytest.mark.django_db
def test_school_groups_search_variant_seoultech():
    """서울과학기술대학교가 인서울 그룹으로 매칭되는지 확인."""
    c = Candidate.objects.create(name="test_서울과기대")
    Education.objects.create(candidate=c, institution="서울과학기술대학교")

    qs = build_search_queryset({"school_groups": ["인서울"]})
    result_ids = set(qs.values_list("id", flat=True))

    assert c.id in result_ids, (
        "서울과학기술대학교 should match via 서울과학기술대 token"
    )


def test_resolve_group_name_normalization():
    """그룹명 정규화: 대소문자, 공백, alias 처리."""
    assert _resolve_group_name("SKY") == "SKY"
    assert _resolve_group_name("sky") == "SKY"
    assert _resolve_group_name("Sky") == "SKY"
    assert _resolve_group_name("이공계명문") == "이공계명문"
    assert _resolve_group_name("이공계 명문") == "이공계명문"
    assert _resolve_group_name("이공계 명문대") == "이공계명문"
    assert _resolve_group_name("이공계명문대") == "이공계명문"
    assert _resolve_group_name("명문대학") == "명문대"
    assert _resolve_group_name("  SKY  ") == "SKY"


@pytest.mark.django_db
def test_school_groups_includes_branch_campus():
    """Branch campus inclusion is intended: Korea Univ Sejong matches SKY."""
    c = Candidate.objects.create(name="test_고려대세종")
    Education.objects.create(candidate=c, institution="고려대학교 세종캠퍼스")

    qs = build_search_queryset({"school_groups": ["SKY"]})
    result_ids = set(qs.values_list("id", flat=True))

    assert c.id in result_ids, "Branch campus should be included (recall-first policy)"
