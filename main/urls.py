from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from projects.views import dashboard, dashboard_actions, dashboard_team

urlpatterns = [
    path("admin/", admin.site.urls),
    # P13: Dashboard — root entry point (must be before accounts.urls include)
    path("", dashboard, name="dashboard"),
    path("dashboard/", dashboard, name="dashboard_explicit"),
    path("dashboard/actions/", dashboard_actions, name="dashboard_actions"),
    path("dashboard/team/", dashboard_team, name="dashboard_team"),
    # Accounts (includes login, settings, etc. at root prefix)
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("clients/", include("clients.urls")),
    path("reference/", include("clients.urls_reference")),
    path("voice/", include("projects.urls_voice")),
    path("projects/", include("projects.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
