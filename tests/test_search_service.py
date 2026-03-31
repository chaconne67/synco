import pytest
from django.contrib.auth import get_user_model

from candidates.models import SearchSession, SearchTurn

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
