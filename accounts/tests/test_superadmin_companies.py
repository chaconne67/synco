import pytest

from accounts.models import User


PENDING_URL = "/superadmin/pending/"


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    resp = client.get(PENDING_URL)
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url


@pytest.mark.django_db
def test_level1_user_gets_403(client):
    u = User.objects.create_user(
        username="u1", email="u1@e.com", password="p!", level=1
    )
    client.force_login(u)
    resp = client.get(PENDING_URL)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_level0_user_redirected_to_pending(client):
    u = User.objects.create_user(
        username="u0", email="u0@e.com", password="p!", level=0
    )
    client.force_login(u)
    resp = client.get(PENDING_URL)
    # level_required redirects level 0 to pending_approval
    assert resp.status_code == 302


@pytest.mark.django_db
def test_level2_user_sees_pending_list(client):
    boss = User.objects.create_user(
        username="boss", email="boss@e.com", password="p!", level=2
    )
    pending = User.objects.create_user(
        username="pending1", email="p1@e.com", password="p!", level=0
    )
    client.force_login(boss)
    resp = client.get(PENDING_URL)
    assert resp.status_code == 200
    assert (
        pending.username.encode() in resp.content
        or pending.email.encode() in resp.content
    )


@pytest.mark.django_db
def test_superuser_sees_pending_list(client):
    su = User.objects.create_user(
        username="su",
        email="su@e.com",
        password="p!",
        is_superuser=True,
        is_staff=True,
    )
    pending = User.objects.create_user(
        username="pending2", email="p2@e.com", password="p!", level=0
    )
    client.force_login(su)
    resp = client.get(PENDING_URL)
    assert resp.status_code == 200
    assert pending.email.encode() in resp.content


@pytest.mark.django_db
def test_level1_user_approve_post_gets_403(client):
    u = User.objects.create_user(
        username="u1b", email="u1b@e.com", password="p!", level=1
    )
    pending = User.objects.create_user(
        username="pend0", email="pend0@e.com", password="p!", level=0
    )
    client.force_login(u)
    resp = client.post(f"/superadmin/approve/{pending.id}/", {"level": "1"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_approve_user_sets_level1(client):
    boss = User.objects.create_user(
        username="boss2", email="boss2@e.com", password="p!", level=2
    )
    pending = User.objects.create_user(
        username="pend3", email="p3@e.com", password="p!", level=0
    )
    client.force_login(boss)
    resp = client.post(f"/superadmin/approve/{pending.id}/", {"level": "1"})
    assert resp.status_code == 302
    pending.refresh_from_db()
    assert pending.level == 1


@pytest.mark.django_db
def test_approve_user_sets_level2(client):
    boss = User.objects.create_user(
        username="boss3", email="boss3@e.com", password="p!", level=2
    )
    pending = User.objects.create_user(
        username="pend4", email="p4@e.com", password="p!", level=0
    )
    client.force_login(boss)
    resp = client.post(f"/superadmin/approve/{pending.id}/", {"level": "2"})
    assert resp.status_code == 302
    pending.refresh_from_db()
    assert pending.level == 2


@pytest.mark.django_db
def test_approve_user_invalid_level_defaults_to_1(client):
    boss = User.objects.create_user(
        username="boss4", email="boss4@e.com", password="p!", level=2
    )
    pending = User.objects.create_user(
        username="pend5", email="p5@e.com", password="p!", level=0
    )
    client.force_login(boss)
    resp = client.post(f"/superadmin/approve/{pending.id}/", {"level": "99"})
    assert resp.status_code == 302
    pending.refresh_from_db()
    assert pending.level == 1


@pytest.mark.django_db
def test_approve_user_does_not_affect_already_active_user(client):
    boss = User.objects.create_user(
        username="boss5", email="boss5@e.com", password="p!", level=2
    )
    active = User.objects.create_user(
        username="active1", email="a1@e.com", password="p!", level=1
    )
    client.force_login(boss)
    # POST approve on a level-1 user should not change their level (filter is level=0)
    client.post(f"/superadmin/approve/{active.id}/", {"level": "2"})
    active.refresh_from_db()
    assert active.level == 1
