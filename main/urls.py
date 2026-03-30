from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("contacts/", include("contacts.urls")),
    path("meetings/", include("meetings.urls")),
    path("intelligence/", include("intelligence.urls")),
    path("candidates/", include("candidates.urls")),
]
