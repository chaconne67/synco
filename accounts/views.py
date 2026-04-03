import httpx
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import User


@login_required
def home(request):
    return redirect("candidate_list")


def login_page(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "accounts/login.html")


def kakao_login(request):
    kakao_auth_url = (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={settings.KAKAO_CLIENT_ID}"
        f"&redirect_uri={settings.KAKAO_REDIRECT_URI}"
        "&response_type=code"
    )
    return redirect(kakao_auth_url)


def kakao_callback(request):
    code = request.GET.get("code")
    if not code:
        return redirect("login")

    # Exchange code for token
    token_resp = httpx.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": settings.KAKAO_CLIENT_ID,
            "client_secret": settings.KAKAO_CLIENT_SECRET,
            "redirect_uri": settings.KAKAO_REDIRECT_URI,
            "code": code,
        },
    )
    if token_resp.status_code != 200:
        return redirect("login")

    access_token = token_resp.json().get("access_token")

    # Get user info
    user_resp = httpx.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if user_resp.status_code != 200:
        return redirect("login")

    kakao_data = user_resp.json()
    kakao_id = kakao_data["id"]
    kakao_account = kakao_data.get("kakao_account", {})
    profile = kakao_account.get("profile", {})

    # Create or get user
    user, created = User.objects.get_or_create(
        kakao_id=kakao_id,
        defaults={
            "username": f"kakao_{kakao_id}",
            "first_name": profile.get("nickname", ""),
        },
    )

    login(request, user, backend="accounts.backends.KakaoBackend")

    return redirect("home")


@login_required
def settings_page(request):
    return render(request, "accounts/settings.html")


def logout_view(request):
    logout(request)
    return redirect("login")


def terms(request):
    """서비스 이용약관 페이지."""
    template = (
        "accounts/partials/terms_content.html"
        if getattr(request, "htmx", None)
        else "accounts/terms.html"
    )
    return render(request, template)


def privacy(request):
    """개인정보처리방침 페이지."""
    template = (
        "accounts/partials/privacy_content.html"
        if getattr(request, "htmx", None)
        else "accounts/privacy.html"
    )
    return render(request, template)
