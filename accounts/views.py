import json

import httpx
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import User


@login_required
def home(request):
    return redirect("/")


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


# --- P18: Gmail integration ---


@login_required
def email_connect(request):
    """Start Gmail OAuth flow with offline access."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRET_PATH,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        redirect_uri=request.build_absolute_uri(reverse("email_callback")),
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    request.session["gmail_oauth_state"] = state
    return redirect(authorization_url)


@login_required
def email_oauth_callback(request):
    """Handle Gmail OAuth callback -> create/update EmailMonitorConfig."""
    from google_auth_oauthlib.flow import Flow

    from .models import EmailMonitorConfig

    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRET_PATH,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        redirect_uri=request.build_absolute_uri(reverse("email_callback")),
        state=request.session.get("gmail_oauth_state"),
    )
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    credentials = flow.credentials
    creds_dict = json.loads(credentials.to_json())

    config, _created = EmailMonitorConfig.objects.get_or_create(
        user=request.user,
        defaults={"gmail_credentials": b""},
    )
    config.set_credentials(creds_dict)
    config.is_active = True
    config.save()

    return redirect(reverse("email_settings"))


@login_required
def email_settings(request):
    """Gmail monitoring settings page."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()

    if request.method == "POST" and config:
        config.filter_labels = request.POST.getlist("filter_labels")
        config.filter_from = [
            e.strip()
            for e in request.POST.get("filter_from", "").split(",")
            if e.strip()
        ]
        config.is_active = request.POST.get("is_active") == "on"
        config.save(
            update_fields=[
                "filter_labels",
                "filter_from",
                "is_active",
                "updated_at",
            ]
        )

    return render(request, "accounts/email_settings.html", {"config": config})


@login_required
def email_disconnect(request):
    """Disconnect Gmail: revoke tokens + deactivate. Preserve imported resumes."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()
    if config:
        try:
            creds = config.get_credentials()
            token = creds.get("token", "")
            if token:
                httpx.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    timeout=10,
                )
        except Exception:
            pass  # Best-effort revocation

        config.delete()

    return redirect(reverse("email_settings"))
