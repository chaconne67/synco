import pytest
from django.urls import reverse

from accounts.models import User


@pytest.mark.django_db
def test_home_level_0_redirects_to_pending(pending_client):
    resp = pending_client.get(reverse("home"))
    assert resp.status_code == 302
    assert resp["Location"].endswith("/accounts/pending/")


@pytest.mark.django_db
def test_home_level_1_redirects_to_dashboard(staff_client):
    resp = staff_client.get(reverse("home"))
    assert resp.status_code == 302
    assert "/dashboard" in resp["Location"]


@pytest.mark.django_db
def test_pending_page_shows_disabled_button_for_level_0(pending_client):
    resp = pending_client.get(reverse("pending_approval"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "승인 요청이 관리자에게 전달" in body
    assert 'data-testid="enter-dashboard-btn"' in body
    assert "disabled" in body


@pytest.mark.django_db
def test_pending_page_button_enabled_after_promotion(client, pending_user):
    client.force_login(pending_user)
    pending_user.level = 1
    pending_user.save()

    resp = client.get(reverse("pending_approval"))
    body = resp.content.decode()
    assert 'data-testid="enter-dashboard-btn"' in body
    assert "cursor-not-allowed" not in body
    assert "opacity-50" not in body


@pytest.mark.django_db
def test_invite_code_url_removed(client):
    from django.urls import NoReverseMatch
    with pytest.raises(NoReverseMatch):
        reverse("invite_code")


# --- Email/password signup + login ---


@pytest.mark.django_db
def test_login_page_renders(client):
    resp = client.get(reverse("login"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "이메일" in body
    assert "비밀번호" in body


@pytest.mark.django_db
def test_signup_page_renders(client):
    resp = client.get(reverse("signup"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "회원가입" in body


@pytest.mark.django_db
def test_signup_creates_level_0_user_and_logs_in(client):
    resp = client.post(
        reverse("signup"),
        {
            "email": "new@example.com",
            "password": "strong-pass-123",
            "password_confirm": "strong-pass-123",
        },
    )
    assert resp.status_code == 302
    u = User.objects.get(email="new@example.com")
    assert u.level == 0
    assert u.is_superuser is False
    assert u.check_password("strong-pass-123")
    # Subsequent request is authenticated
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_signup_rejects_mismatched_passwords(client):
    resp = client.post(
        reverse("signup"),
        {
            "email": "bad@example.com",
            "password": "aaaaaaaa",
            "password_confirm": "bbbbbbbb",
        },
    )
    assert resp.status_code == 200
    assert "비밀번호가 일치하지 않습니다" in resp.content.decode()
    assert not User.objects.filter(email="bad@example.com").exists()


@pytest.mark.django_db
def test_signup_rejects_short_password(client):
    resp = client.post(
        reverse("signup"),
        {
            "email": "short@example.com",
            "password": "1234",
            "password_confirm": "1234",
        },
    )
    assert resp.status_code == 200
    assert "8자 이상" in resp.content.decode()
    assert not User.objects.filter(email="short@example.com").exists()


@pytest.mark.django_db
def test_signup_rejects_duplicate_email(client):
    User.objects.create_user(
        username="dup@example.com", email="dup@example.com", password="xxxxxxxx"
    )
    resp = client.post(
        reverse("signup"),
        {
            "email": "dup@example.com",
            "password": "yyyyyyyy",
            "password_confirm": "yyyyyyyy",
        },
    )
    assert resp.status_code == 200
    assert "이미 가입된" in resp.content.decode()
    assert User.objects.filter(email="dup@example.com").count() == 1


@pytest.mark.django_db
def test_login_authenticates_valid_credentials(client):
    User.objects.create_user(
        username="login@example.com",
        email="login@example.com",
        password="right-pass",
    )
    resp = client.post(
        reverse("login"),
        {"email": "login@example.com", "password": "right-pass"},
    )
    assert resp.status_code == 302
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_login_rejects_wrong_password(client):
    User.objects.create_user(
        username="wrong@example.com",
        email="wrong@example.com",
        password="right-pass",
    )
    resp = client.post(
        reverse("login"),
        {"email": "wrong@example.com", "password": "bad-pass"},
    )
    assert resp.status_code == 200
    assert "올바르지 않습니다" in resp.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_kakao_urls_removed(client):
    from django.urls import NoReverseMatch
    with pytest.raises(NoReverseMatch):
        reverse("kakao_login")
    with pytest.raises(NoReverseMatch):
        reverse("kakao_callback")
