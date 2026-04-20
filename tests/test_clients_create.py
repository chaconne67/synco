import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from clients.models import Client
from clients.services.client_create import (
    apply_logo_upload,
    normalize_contact_persons,
)


@pytest.fixture
def legacy_org(db):
    """Temporary shim until T7 drops organization FK."""
    from accounts.models import Organization

    return Organization.objects.create(name="Legacy")


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
def test_apply_logo_upload_saves_file(legacy_org):
    c = Client.objects.create(organization=legacy_org, name="A")
    f = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")
    apply_logo_upload(c, f)
    c.refresh_from_db()
    assert c.logo.name.startswith("clients/logos/")


@pytest.mark.django_db
def test_apply_logo_upload_delete_flag(legacy_org):
    c = Client.objects.create(organization=legacy_org, name="A")
    f = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")
    apply_logo_upload(c, f)
    apply_logo_upload(c, None, delete=True)
    c.refresh_from_db()
    assert not c.logo
