from unittest.mock import patch

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
    assert "opacity-50" not in body or "disabled" not in body


@pytest.mark.django_db
def test_invite_code_url_removed(client):
    from django.urls import NoReverseMatch
    with pytest.raises(NoReverseMatch):
        reverse("invite_code")


@pytest.mark.django_db
@patch("accounts.views.httpx.get")
@patch("accounts.views.httpx.post")
def test_kakao_callback_creates_level_0_user(mock_post, mock_get, client):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json = lambda: {"access_token": "T"}
    mock_get.return_value.status_code = 200
    mock_get.return_value.json = lambda: {
        "id": 12345,
        "kakao_account": {"profile": {"nickname": "홍길동"}},
    }

    resp = client.get(reverse("kakao_callback") + "?code=abc")

    assert resp.status_code == 302
    assert resp["Location"].endswith("/")

    u = User.objects.get(kakao_id=12345)
    assert u.level == 0
    assert u.is_superuser is False
