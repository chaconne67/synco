import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from clients.models import Client, IndustryCategory


@pytest.fixture
def existing_client():
    return Client.objects.create(
        name="ExistingCo",
        industry=IndustryCategory.IT_SW.value,
    )


@pytest.mark.django_db
def test_create_client_minimal(boss_client):
    """POST to client_create with minimal data → 302 + Client created."""
    url = reverse("clients:client_create")
    resp = boss_client.post(
        url,
        data={
            "name": "New Co",
            "industry": IndustryCategory.IT_SW.value,
            "contact_persons_json": "[]",
        },
    )
    assert resp.status_code == 302
    assert Client.objects.filter(name="New Co").exists()


@pytest.mark.django_db
def test_update_client_website(boss_client, existing_client):
    """POST to client_update with updated website → saved to DB."""
    url = reverse("clients:client_update", kwargs={"pk": existing_client.pk})
    resp = boss_client.post(
        url,
        data={
            "name": existing_client.name,
            "industry": existing_client.industry,
            "website": "https://example.com",
            "contact_persons_json": "[]",
        },
    )
    assert resp.status_code == 302
    existing_client.refresh_from_db()
    assert existing_client.website == "https://example.com"


@pytest.mark.django_db
def test_create_rejects_invalid_logo_ext(boss_client):
    """POST with .exe logo → form re-renders (200) with validation error, no Client created."""
    import io
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    exe_file = SimpleUploadedFile("bad.exe", buf.getvalue(), content_type="image/png")

    url = reverse("clients:client_create")
    resp = boss_client.post(
        url,
        data={
            "name": "BadLogoClient",
            "industry": IndustryCategory.ETC.value,
            "contact_persons_json": "[]",
            "logo": exe_file,
        },
    )
    assert resp.status_code == 200
    assert not Client.objects.filter(name="BadLogoClient").exists()
    body = resp.content.decode()
    assert "허용되지 않" in body


@pytest.mark.django_db
def test_contact_persons_round_trip(boss_client, existing_client):
    """POST to client_update with contact_persons_json → persisted and readable."""
    url = reverse("clients:client_update", kwargs={"pk": existing_client.pk})
    cp = json.dumps(
        [{"name": "Kim", "position": "CEO", "phone": "010", "email": "k@x.com"}]
    )
    resp = boss_client.post(
        url,
        data={
            "name": existing_client.name,
            "industry": existing_client.industry,
            "contact_persons_json": cp,
        },
    )
    assert resp.status_code == 302
    existing_client.refresh_from_db()
    assert existing_client.contact_persons[0]["name"] == "Kim"
    assert existing_client.contact_persons[0]["position"] == "CEO"
