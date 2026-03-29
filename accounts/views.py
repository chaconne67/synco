from datetime import timedelta

import httpx
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from contacts.models import Contact, Task
from intelligence.models import AnalysisJob, Brief, FortunateInsight
from meetings.models import Meeting

from .models import User


@login_required
def home(request):
    user = request.user
    if not user.role:
        return redirect("role_select")

    if user.role == User.Role.FC:
        return _fc_dashboard(request)
    return _ceo_dashboard(request)


def _fc_dashboard(request):
    today = timezone.localdate()
    now = timezone.now()
    week_end = today + timedelta(days=7)

    # Section 1: 오늘의 업무
    all_pending = Task.objects.filter(
        fc=request.user,
        is_completed=False,
    ).select_related("contact")
    total_task_count = all_pending.count()
    pending_tasks = all_pending[:10]

    # Section 2: 오늘 미팅 → 없으면 이번주
    todays_meetings = Meeting.objects.filter(
        fc=request.user,
        scheduled_at__date=today,
        status=Meeting.Status.SCHEDULED,
    ).select_related("contact")

    show_week_meetings = not todays_meetings.exists()
    week_meetings = Meeting.objects.none()
    if show_week_meetings:
        week_meetings = Meeting.objects.filter(
            fc=request.user,
            scheduled_at__date__range=(today, week_end),
            status=Meeting.Status.SCHEDULED,
        ).select_related("contact")

    # Section 3: AI 브리핑 (latest)
    latest_brief = (
        Brief.objects.filter(fc=request.user)
        .select_related("contact")
        .first()
    )

    # Section 4: Feel Lucky
    from django.db.models import Q
    fortunate_insights = FortunateInsight.objects.filter(
        fc=request.user,
        is_dismissed=False,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=now),
    ).select_related("contact")[:5]

    # Section 5: 분석
    contacts = Contact.objects.filter(fc=request.user)
    total_contacts = contacts.count()

    tier_counts_raw = (
        contacts.exclude(relationship_tier="")
        .values("relationship_tier")
        .annotate(count=Count("id"))
    )
    tier_summary = {item["relationship_tier"]: item["count"] for item in tier_counts_raw}
    unscored = total_contacts - sum(tier_summary.values())
    if unscored > 0:
        tier_summary["gray"] = tier_summary.get("gray", 0) + unscored

    managed = tier_summary.get("gold", 0) + tier_summary.get("green", 0)
    management_rate = round(managed / total_contacts * 100) if total_contacts else 0

    attention_contacts = contacts.filter(
        relationship_tier__in=["red", "yellow"],
    ).order_by("relationship_score")[:5]

    latest_job = AnalysisJob.objects.filter(fc=request.user).first()

    # Analysis progress (embedding-based)
    from intelligence.models import ContactEmbedding
    embedding_count = ContactEmbedding.objects.filter(contact__fc=request.user).count()
    analysis_in_progress = total_contacts > 0 and embedding_count < total_contacts * 0.95
    analysis_progress = round(embedding_count / total_contacts * 100) if total_contacts else 0

    return render(request, "accounts/dashboard_fc.html", {
        # Section 1
        "pending_tasks": pending_tasks,
        "total_task_count": total_task_count,
        # Section 2
        "todays_meetings": todays_meetings,
        "show_week_meetings": show_week_meetings,
        "week_meetings": week_meetings,
        # Section 3
        "latest_brief": latest_brief,
        # Section 4
        "fortunate_insights": fortunate_insights,
        # Section 5
        "tier_summary": tier_summary,
        "management_rate": management_rate,
        "total_contacts": total_contacts,
        "attention_contacts": attention_contacts,
        "latest_job": latest_job,
        "analysis_in_progress": analysis_in_progress,
        "analysis_progress": analysis_progress,
    })


def _ceo_dashboard(request):
    return render(request, "accounts/dashboard_ceo.html")


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

    if not user.role:
        return redirect("role_select")
    return redirect("home")


@login_required
def role_select(request):
    if request.method == "POST":
        role = request.POST.get("role")
        if role in [User.Role.FC, User.Role.CEO]:
            request.user.role = role
            request.user.save(update_fields=["role"])
            return redirect("home")

    return render(request, "accounts/role_select.html")


@login_required
def settings_page(request):
    return render(request, "accounts/settings.html")


def logout_view(request):
    logout(request)
    return redirect("login")
