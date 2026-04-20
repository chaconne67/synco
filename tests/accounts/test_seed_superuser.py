import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User


@pytest.mark.django_db
def test_seed_superuser_creates_user(settings):
    settings.SYNCO_SUPERUSER_EMAIL = "chaconne67@gmail.com"
    call_command("seed_superuser")
    u = User.objects.get(email="chaconne67@gmail.com")
    assert u.level == 2
    assert u.is_superuser is True
    assert u.is_staff is True


@pytest.mark.django_db
def test_seed_superuser_is_idempotent(settings):
    settings.SYNCO_SUPERUSER_EMAIL = "chaconne67@gmail.com"
    call_command("seed_superuser")
    call_command("seed_superuser")
    assert User.objects.filter(email="chaconne67@gmail.com").count() == 1


@pytest.mark.django_db
def test_seed_superuser_raises_if_email_unset(settings):
    settings.SYNCO_SUPERUSER_EMAIL = ""
    with pytest.raises(CommandError):
        call_command("seed_superuser")


@pytest.mark.django_db
def test_seed_superuser_promotes_existing_user(settings):
    settings.SYNCO_SUPERUSER_EMAIL = "chaconne67@gmail.com"
    User.objects.create_user(
        username="existing", email="chaconne67@gmail.com", password="x", level=0
    )
    call_command("seed_superuser")
    u = User.objects.get(email="chaconne67@gmail.com")
    assert u.level == 2
    assert u.is_superuser is True
