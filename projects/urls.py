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
    # P05: 탭 URL
    path(
        "<uuid:pk>/tab/overview/",
        views.project_tab_overview,
        name="project_tab_overview",
    ),
    path(
        "<uuid:pk>/tab/search/",
        views.project_tab_search,
        name="project_tab_search",
    ),
    path(
        "<uuid:pk>/tab/contacts/",
        views.project_tab_contacts,
        name="project_tab_contacts",
    ),
    path(
        "<uuid:pk>/tab/submissions/",
        views.project_tab_submissions,
        name="project_tab_submissions",
    ),
    path(
        "<uuid:pk>/tab/interviews/",
        views.project_tab_interviews,
        name="project_tab_interviews",
    ),
    path(
        "<uuid:pk>/tab/offers/",
        views.project_tab_offers,
        name="project_tab_offers",
    ),
    # P06: 컨택 관리
    path(
        "<uuid:pk>/contacts/new/",
        views.contact_create,
        name="contact_create",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:contact_pk>/edit/",
        views.contact_update,
        name="contact_update",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:contact_pk>/delete/",
        views.contact_delete,
        name="contact_delete",
    ),
    path(
        "<uuid:pk>/contacts/reserve/",
        views.contact_reserve,
        name="contact_reserve",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:contact_pk>/release/",
        views.contact_release_lock,
        name="contact_release_lock",
    ),
    path(
        "<uuid:pk>/contacts/check-duplicate/",
        views.contact_check_duplicate,
        name="contact_check_duplicate",
    ),
]
