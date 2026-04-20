from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home
from accounts.views_team import team_list
from projects.views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("hijack/", include("hijack.urls")),
    # Root: onboarding router (routes by membership status)
    path("", home, name="home"),
    # Dashboard: explicit path only (protected by membership_required in t04)
    path("dashboard/", dashboard, name="dashboard"),
    path("team/", team_list, name="team"),
    # Accounts (includes login, settings, etc. at root prefix)
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("clients/", include("clients.urls")),
    path("reference/", include("clients.urls_reference")),
    path("voice/", include("projects.urls_voice")),
    path("projects/", include("projects.urls")),
    path("telegram/", include("projects.urls_telegram")),
    path("org/", include("accounts.urls_org")),
    path("superadmin/", include("accounts.urls_superadmin")),
    path("news/", include("projects.urls_news")),
]

if settings.DEBUG:
    from django.views.static import serve

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # UI 목업 참조용 (assets/ui-sample/*.html) — DEBUG에서만 노출
    urlpatterns += [
        path(
            "mockup/<path:path>",
            serve,
            {"document_root": settings.BASE_DIR / "assets" / "ui-sample"},
        ),
    ]
