import pytest
from django.contrib.auth import get_user_model
from unittest.mock import patch

from candidates.models import SearchSession, SearchTurn, Candidate, Category
from candidates.services.search import (
    parse_search_query,
    execute_structured_search,
)

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="test1234")


@pytest.mark.django_db
def test_create_search_session(user):
    session = SearchSession.objects.create(user=user)
    assert session.is_active is True
    assert session.current_filters == {}


@pytest.mark.django_db
def test_create_search_turn(user):
    session = SearchSession.objects.create(user=user)
    turn = SearchTurn.objects.create(
        session=session,
        turn_number=1,
        input_type="text",
        user_text="회계 10년차 이상",
        ai_response="30명을 찾았습니다",
        filters_applied={"category": "Accounting", "min_experience_years": 10},
        result_count=30,
    )
    assert turn.session == session
    assert turn.filters_applied["category"] == "Accounting"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def candidate_a(db, category):
    c = Candidate.objects.create(
        name="강솔찬",
        current_company="현대엠시트",
        current_position="회계팀장",
        total_experience_years=12,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.fixture
def candidate_b(db, category):
    c = Candidate.objects.create(
        name="김영희",
        current_company="스타트업",
        current_position="인턴",
        total_experience_years=1,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.mark.django_db
def test_execute_structured_search_by_category(candidate_a, candidate_b, category):
    filters = {"category": "Accounting"}
    results = execute_structured_search(filters)
    assert candidate_a in results
    assert candidate_b in results


@pytest.mark.django_db
def test_execute_structured_search_min_experience(candidate_a, candidate_b):
    filters = {"min_experience_years": 10}
    results = execute_structured_search(filters)
    assert candidate_a in results
    assert candidate_b not in results


@pytest.mark.django_db
def test_execute_structured_search_company(candidate_a, candidate_b):
    filters = {"companies_include": ["현대"]}
    results = execute_structured_search(filters)
    assert candidate_a in results
    assert candidate_b not in results


@pytest.mark.django_db
@patch("candidates.services.search.call_llm_json")
def test_parse_search_query(mock_llm):
    mock_llm.return_value = {
        "filters": {
            "category": "Accounting",
            "min_experience_years": 10,
        },
        "semantic_query": "회계 10년차 이상",
        "action": "new",
        "ai_message": "회계 분야 10년 이상 경력 후보자를 찾겠습니다.",
    }
    result = parse_search_query("회계 10년차 이상 찾아줘", current_filters={})
    assert result["filters"]["category"] == "Accounting"
    assert result["action"] == "new"
