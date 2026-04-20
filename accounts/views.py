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
    """Root redirect -- route by user.level."""
    user = request.user
    if user.is_superuser or user.level >= 1:
        return redirect("dashboard")
    return redirect("pending_approval")


@login_required
def pending_approval_page(request):
    """Level 0 대기 페이지. Level 1 이상이면 버튼 활성화 상태로 렌더."""
    user = request.user
    activated = user.is_superuser or user.level >= 1
    return render(
        request,
        "accounts/pending_approval.html",
        {"activated": activated},
    )


def landing_page(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "accounts/landing.html")


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
        return redirect("landing")

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
        return redirect("landing")

    access_token = token_resp.json().get("access_token")

    # Get user info
    user_resp = httpx.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if user_resp.status_code != 200:
        return redirect("landing")

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
    return redirect("settings_profile")


def _is_tab_switch(request):
    """Check if this is an HTMX tab switch (targeting #settings-content)."""
    return (
        getattr(request, "htmx", None)
        and request.headers.get("HX-Target") == "settings-content"
    )


@login_required
def settings_profile(request):
    """GET /accounts/settings/profile/ — Profile tab."""
    context = {"active_tab": "profile"}
    if _is_tab_switch(request):
        return render(request, "accounts/partials/settings_content.html", context)
    return render(request, "accounts/settings.html", context)


@login_required
def settings_email(request):
    """GET/POST /accounts/settings/email/ — Email tab."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()

    if request.method == "POST" and config:
        config.filter_from = [
            e.strip()
            for e in request.POST.get("filter_from", "").split(",")
            if e.strip()
        ]
        config.is_active = request.POST.get("is_active") == "on"
        config.save(update_fields=["filter_from", "is_active", "updated_at"])

    context = {"config": config, "active_tab": "email"}

    if _is_tab_switch(request) or (
        getattr(request, "htmx", None) and request.method == "POST"
    ):
        return render(request, "accounts/partials/settings_email.html", context)
    return render(
        request,
        "accounts/settings.html",
        {
            **context,
            "tab_template": "accounts/partials/settings_email.html",
        },
    )


@login_required
def settings_telegram(request):
    """GET /accounts/settings/telegram/ — Telegram tab."""
    from .models import TelegramBinding

    try:
        binding = TelegramBinding.objects.get(user=request.user)
        is_bound = binding.is_active
        verified_at = binding.verified_at
    except TelegramBinding.DoesNotExist:
        is_bound = False
        verified_at = None

    context = {
        "is_bound": is_bound,
        "verified_at": verified_at,
        "active_tab": "telegram",
    }

    if _is_tab_switch(request):
        return render(request, "accounts/partials/settings_telegram.html", context)
    return render(
        request,
        "accounts/settings.html",
        {
            **context,
            "tab_template": "accounts/partials/settings_telegram.html",
        },
    )


@login_required
def settings_notify(request):
    """GET/POST /accounts/settings/notify/ — Notification preferences tab."""
    from .forms import NotificationPreferenceForm
    from .models import NotificationPreference

    pref, _created = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = NotificationPreferenceForm(request.POST)
        if form.is_valid():
            pref.preferences = form.to_preferences()
            pref.save(update_fields=["preferences", "updated_at"])

    form = NotificationPreferenceForm()
    form.load_from_preferences(pref.preferences)

    context = {"form": form, "active_tab": "notify"}

    if _is_tab_switch(request) or (
        getattr(request, "htmx", None) and request.method == "POST"
    ):
        return render(request, "accounts/partials/settings_notify.html", context)
    return render(
        request,
        "accounts/settings.html",
        {
            **context,
            "tab_template": "accounts/partials/settings_notify.html",
        },
    )


def logout_view(request):
    logout(request)
    return redirect("landing")


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

    return redirect(reverse("settings_email"))


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

    return redirect(reverse("settings_email"))
