from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", lambda r: redirect("/candidates/"), name="root"),
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("clients/", include("clients.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
