from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", lambda r: redirect("/candidates/"), name="root"),
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("contacts/", include("contacts.urls")),
    path("meetings/", include("meetings.urls")),
    path("intelligence/", include("intelligence.urls")),
]
