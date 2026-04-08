from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("new/", views.project_create, name="project_create"),
    path("<uuid:pk>/", views.project_detail, name="project_detail"),
    path("<uuid:pk>/edit/", views.project_update, name="project_update"),
    path("<uuid:pk>/delete/", views.project_delete, name="project_delete"),
    path("<uuid:pk>/status/", views.status_update, name="status_update"),
    # P03a: JD 분석
    path("<uuid:pk>/analyze-jd/", views.analyze_jd, name="analyze_jd"),
    path("<uuid:pk>/jd-results/", views.jd_results, name="jd_results"),
    path("<uuid:pk>/drive-picker/", views.drive_picker, name="drive_picker"),
    path(
        "<uuid:pk>/start-search/",
        views.start_search_session,
        name="start_search_session",
    ),
    path("<uuid:pk>/matching/", views.jd_matching_results, name="jd_matching_results"),
]
