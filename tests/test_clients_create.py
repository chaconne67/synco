import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Organization
from clients.models import Client
from clients.services.client_create import (
    apply_logo_upload,
    normalize_contact_persons,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


def test_normalize_contact_persons_drops_empty_rows():
    raw = [
        {"name": "A", "position": "CEO", "phone": "", "email": ""},
        {"name": "", "position": "", "phone": "", "email": ""},
        {"name": "  ", "position": "x", "phone": "", "email": ""},
        {"name": "B", "position": "", "phone": "010", "email": ""},
    ]
    out = normalize_contact_persons(raw)
    assert len(out) == 2
    assert out[0]["name"] == "A"
    assert out[1]["name"] == "B"


def test_normalize_contact_persons_preserves_schema():
    raw = [{"name": "A", "position": "CEO", "phone": "010", "email": "a@x.com", "extra": "drop"}]
    out = normalize_contact_persons(raw)
    assert set(out[0].keys()) == {"name", "position", "phone", "email"}


@pytest.mark.django_db
def test_apply_logo_upload_saves_file(org):
    c = Client.objects.create(organization=org, name="A")
    f = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")
    apply_logo_upload(c, f)
    c.refresh_from_db()
    assert c.logo.name.startswith("clients/logos/")


@pytest.mark.django_db
def test_apply_logo_upload_delete_flag(org):
    c = Client.objects.create(organization=org, name="A")
    f = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")
    apply_logo_upload(c, f)
    apply_logo_upload(c, None, delete=True)
    c.refresh_from_db()
    assert not c.logo
