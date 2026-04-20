import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_hijack_urls_registered(client):
    url = reverse("hijack:acquire")
    assert url.startswith("/hijack/")


@pytest.mark.django_db
def test_superuser_can_hijack_staff_user(client, dev_user, staff_user):
    client.force_login(dev_user)

    resp = client.post(
        reverse("hijack:acquire"),
        {"user_pk": str(staff_user.pk), "next": "/"},
    )
    assert resp.status_code == 302

    whoami = client.get("/")
    session_user_pk = client.session.get("_auth_user_id")
    assert str(session_user_pk) == str(staff_user.pk)
