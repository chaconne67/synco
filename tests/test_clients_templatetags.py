import pytest

from accounts.models import Organization
from clients.models import Client
from clients.templatetags.clients_tags import (
    client_initials,
    logo_class,
    size_badge_class,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


def test_size_badge_class_mapping():
    assert size_badge_class("대기업") == "badge enterprise"
    assert size_badge_class("중견") == "badge midcap"
    assert size_badge_class("중소") == "badge sme"
    assert size_badge_class("외국계") == "badge foreign"
    assert size_badge_class("스타트업") == "badge startup"
    assert size_badge_class("") == ""
    assert size_badge_class(None) == ""


def test_client_initials_single_word():
    assert client_initials("SKBP") == "SK"


def test_client_initials_korean():
    assert client_initials("한독") == "한독"


def test_client_initials_long():
    assert client_initials("Vatech 그룹") == "VA"


@pytest.mark.django_db
def test_logo_class_deterministic(org):
    c1 = Client.objects.create(organization=org, name="A")
    c2 = Client.objects.create(organization=org, name="B")
    assert logo_class(c1) == logo_class(c1)
    assert logo_class(c1) in {f"client-logo-{i}" for i in range(1, 9)}
