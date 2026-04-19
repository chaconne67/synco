import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import Membership, Organization, User
from clients.models import Client, IndustryCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org(db):
    return Organization.objects.create(name="FormTestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="form_owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def existing_client(org):
    return Client.objects.create(
        organization=org,
        name="ExistingCo",
        industry=IndustryCategory.IT_SW.value,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_client_minimal(org, logged_in):
    """POST to client_create with minimal data → 302 + Client created."""
    url = reverse("clients:client_create")
    resp = logged_in.post(url, data={
        "name": "New Co",
        "industry": IndustryCategory.IT_SW.value,
        "contact_persons_json": "[]",
    })
    assert resp.status_code == 302
    assert Client.objects.filter(name="New Co", organization=org).exists()


@pytest.mark.django_db
def test_update_client_website(org, logged_in, existing_client):
    """POST to client_update with updated website → saved to DB."""
    url = reverse("clients:client_update", kwargs={"pk": existing_client.pk})
    resp = logged_in.post(url, data={
        "name": existing_client.name,
        "industry": existing_client.industry,
        "website": "https://example.com",
        "contact_persons_json": "[]",
    })
    assert resp.status_code == 302
    existing_client.refresh_from_db()
    assert existing_client.website == "https://example.com"


@pytest.mark.django_db
def test_create_rejects_invalid_logo_ext(org, logged_in):
    """POST with .exe logo → form re-renders (200) with validation error, no Client created.

    Django's built-in validate_image_file_extension fires before clean_logo for truly
    invalid-extension files, so the error message may be Django's own Korean translation
    ("허용되지 않습니다") rather than our custom message ("허용되지 않는 파일 형식입니다").
    Both contain "허용되지 않". The important invariant is: 200 + no Client created.
    """
    import io
    from PIL import Image as PILImage

    # Build a valid 1×1 PNG so Pillow passes, but give it a .exe extension so the
    # extension validator (Django's or ours) rejects it.
    buf = io.BytesIO()
    PILImage.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    exe_file = SimpleUploadedFile("bad.exe", buf.getvalue(), content_type="image/png")

    url = reverse("clients:client_create")
    resp = logged_in.post(url, data={
        "name": "BadLogoClient",
        "industry": IndustryCategory.ETC.value,
        "contact_persons_json": "[]",
        "logo": exe_file,
    })
    # Form should re-render with 200 and NOT create the client
    assert resp.status_code == 200
    assert not Client.objects.filter(name="BadLogoClient").exists()
    body = resp.content.decode()
    # Either our custom validator or Django's built-in extension validator fired —
    # both produce a Korean message containing "허용되지 않"
    assert "허용되지 않" in body


@pytest.mark.django_db
def test_contact_persons_round_trip(org, logged_in, existing_client):
    """POST to client_update with contact_persons_json → persisted and readable."""
    url = reverse("clients:client_update", kwargs={"pk": existing_client.pk})
    cp = json.dumps([{"name": "Kim", "position": "CEO", "phone": "010", "email": "k@x.com"}])
    resp = logged_in.post(url, data={
        "name": existing_client.name,
        "industry": existing_client.industry,
        "contact_persons_json": cp,
    })
    assert resp.status_code == 302
    existing_client.refresh_from_db()
    assert existing_client.contact_persons[0]["name"] == "Kim"
    assert existing_client.contact_persons[0]["position"] == "CEO"
