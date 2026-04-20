import json

import httpx
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import User


def home(request):
    """Root: anonymous → 랜딩, authenticated → level 별 라우팅."""
    user = request.user
    if not user.is_authenticated:
        return render(request, "accounts/landing.html")
    if user.is_superuser or user.level >= 1:
        return redirect("dashboard")
    return redirect("pending_approval")


def landing_page(request):
    """공개 마케팅 랜딩 (로그인 여부 무관)."""
    return render(request, "accounts/landing.html")


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


def login_view(request):
    """Email + password login."""
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=email, password=password)
        if user is None:
            error = "이메일 또는 비밀번호가 올바르지 않습니다."
        else:
            login(request, user)
            return redirect("home")

    return render(request, "accounts/login.html", {"error": error})


def signup_view(request):
    """Email + password signup. New users start at level=0 (pending)."""
    if request.user.is_authenticated:
        return redirect("home")

    error = None
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        password_confirm = request.POST.get("password_confirm") or ""

        if not email or "@" not in email:
            error = "유효한 이메일을 입력해주세요."
        elif len(password) < 8:
            error = "비밀번호는 8자 이상이어야 합니다."
        elif password != password_confirm:
            error = "비밀번호가 일치하지 않습니다."
        elif User.objects.filter(email=email).exists():
            error = "이미 가입된 이메일입니다."
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
            )
            login(request, user)
            return redirect("home")

    return render(request, "accounts/signup.html", {"error": error})


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
