import json
from unittest.mock import patch

import pytest

from candidates.models import Candidate, Career, Category, Certification, Education
from candidates.services.search import has_active_filters, parse_and_search


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
    Education.objects.create(candidate=matching, institution="서울대학교", major="경영학")
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
