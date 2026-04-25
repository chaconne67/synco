import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_new_user_defaults_to_level_0():
    u = User.objects.create_user(username="u1", password="x")
    assert u.level == 0


@pytest.mark.django_db
def test_user_level_choices_accepted():
    u = User.objects.create_user(username="u2", password="x", level=1)
    u.refresh_from_db()
    assert u.level == 1

    u.level = 2
    u.save()
    u.refresh_from_db()
    assert u.level == 2


@pytest.mark.django_db
def test_display_name_uses_korean_last_name_first_name_order():
    u = User.objects.create_user(
        username="hong",
        password="x",
        last_name="홍",
        first_name="길동",
    )

    assert u.display_name == "홍길동"
    assert u.display_initial == "홍"
