from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home
from projects.views import (
    dashboard,
    dashboard_actions,
    dashboard_team,
    dashboard_todo_partial,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Root: onboarding router (routes by membership status)
    path("", home, name="home"),
    # Dashboard: explicit path only (protected by membership_required in t04)
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/todo/", dashboard_todo_partial, name="dashboard_todo"),
    path("dashboard/actions/", dashboard_actions, name="dashboard_actions"),
    path("dashboard/team/", dashboard_team, name="dashboard_team"),
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
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
