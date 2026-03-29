from django.urls import path

from . import views

app_name = "intelligence"

urlpatterns = [
    path("briefs/<uuid:contact_pk>/", views.brief_detail, name="brief_detail"),
    path(
        "briefs/<uuid:contact_pk>/generate/",
        views.brief_generate,
        name="brief_generate",
    ),
    path("matches/", views.match_list, name="match_list"),
    path("matches/<uuid:pk>/", views.match_detail, name="match_detail"),
    # Analysis
    path("analysis/trigger/", views.analysis_trigger, name="analysis_trigger"),
    path("analysis/status/<uuid:job_pk>/", views.analysis_status, name="analysis_status"),
    # Dashboard briefing (lazy-load)
    path("dashboard-briefing/", views.dashboard_briefing, name="dashboard_briefing"),
    # Report modal
    path("report/<uuid:contact_pk>/", views.contact_report, name="contact_report"),
    path("report/<uuid:contact_pk>/analysis/", views.contact_report_analysis, name="contact_report_analysis"),
    # Import analysis polling
    path("analysis/import-status/<uuid:batch_id>/", views.import_analysis_status, name="import_analysis_status"),
    # Insights
    path("insights/<uuid:pk>/dismiss/", views.dismiss_insight, name="dismiss_insight"),
]
