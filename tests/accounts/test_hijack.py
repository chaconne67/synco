import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_superuser_can_hijack_staff_user(client, dev_user, staff_user):
    client.force_login(dev_user)

    resp = client.post(
        reverse("hijack:acquire"),
        {"user_pk": str(staff_user.pk), "next": "/"},
    )
    assert resp.status_code == 302
    assert str(client.session.get("_auth_user_id")) == str(staff_user.pk)


@pytest.mark.django_db
def test_non_superuser_cannot_hijack(client, staff_user, boss_user):
    client.force_login(staff_user)

    resp = client.post(
        reverse("hijack:acquire"),
        {"user_pk": str(boss_user.pk), "next": "/"},
    )
    assert resp.status_code in (302, 403)
    assert str(client.session.get("_auth_user_id")) == str(staff_user.pk)
