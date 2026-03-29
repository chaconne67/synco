from django.urls import path

from . import views

app_name = "meetings"

urlpatterns = [
    path("", views.meeting_list, name="list"),
    path("new/", views.meeting_create, name="create"),
    path("<uuid:pk>/", views.meeting_detail, name="detail"),
    path("<uuid:pk>/edit/", views.meeting_edit, name="edit"),
    path("<uuid:pk>/cancel/", views.meeting_cancel, name="cancel"),
    path("<uuid:pk>/delete/", views.meeting_delete, name="delete"),
]
