import pytest


@pytest.fixture
def user(db):
    from accounts.models import User

    return User.objects.create_user(
        username="testfc",
        kakao_id=123456789,
        role="fc",
    )


@pytest.fixture
def contact(db, user):
    from contacts.models import Contact

    return Contact.objects.create(
        fc=user,
        name="테스트고객",
        company_name="(주)테스트",
        industry="제조업",
    )
