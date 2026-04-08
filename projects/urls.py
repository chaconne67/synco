from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    # P11: Collision check (must be before "new/" to avoid URL conflicts)
    path(
        "new/check-collision/",
        views.project_check_collision,
        name="project_check_collision",
    ),
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
    # P07: Submission 관리
    path(
        "<uuid:pk>/submissions/new/",
        views.submission_create,
        name="submission_create",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/edit/",
        views.submission_update,
        name="submission_update",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/delete/",
        views.submission_delete,
        name="submission_delete",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/submit/",
        views.submission_submit,
        name="submission_submit",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/feedback/",
        views.submission_feedback,
        name="submission_feedback",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/download/",
        views.submission_download,
        name="submission_download",
    ),
    # P08: Draft 파이프라인
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/",
        views.submission_draft,
        name="submission_draft",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/generate/",
        views.draft_generate,
        name="draft_generate",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/consultation/",
        views.draft_consultation,
        name="draft_consultation",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/consultation/audio/",
        views.draft_consultation_audio,
        name="draft_consultation_audio",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/finalize/",
        views.draft_finalize,
        name="draft_finalize",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/review/",
        views.draft_review,
        name="draft_review",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/convert/",
        views.draft_convert,
        name="draft_convert",
    ),
    path(
        "<uuid:pk>/submissions/<uuid:sub_pk>/draft/preview/",
        views.draft_preview,
        name="draft_preview",
    ),
    # P09: Interview 관리
    path(
        "<uuid:pk>/interviews/new/",
        views.interview_create,
        name="interview_create",
    ),
    path(
        "<uuid:pk>/interviews/<uuid:interview_pk>/edit/",
        views.interview_update,
        name="interview_update",
    ),
    path(
        "<uuid:pk>/interviews/<uuid:interview_pk>/delete/",
        views.interview_delete,
        name="interview_delete",
    ),
    path(
        "<uuid:pk>/interviews/<uuid:interview_pk>/result/",
        views.interview_result,
        name="interview_result",
    ),
    # P09: Offer 관리
    path(
        "<uuid:pk>/offers/new/",
        views.offer_create,
        name="offer_create",
    ),
    path(
        "<uuid:pk>/offers/<uuid:offer_pk>/edit/",
        views.offer_update,
        name="offer_update",
    ),
    path(
        "<uuid:pk>/offers/<uuid:offer_pk>/delete/",
        views.offer_delete,
        name="offer_delete",
    ),
    path(
        "<uuid:pk>/offers/<uuid:offer_pk>/accept/",
        views.offer_accept,
        name="offer_accept",
    ),
    path(
        "<uuid:pk>/offers/<uuid:offer_pk>/reject/",
        views.offer_reject,
        name="offer_reject",
    ),
    # P10: Posting 관리
    path(
        "<uuid:pk>/posting/generate/",
        views.posting_generate,
        name="posting_generate",
    ),
    path(
        "<uuid:pk>/posting/edit/",
        views.posting_edit,
        name="posting_edit",
    ),
    path(
        "<uuid:pk>/posting/download/",
        views.posting_download,
        name="posting_download",
    ),
    path(
        "<uuid:pk>/posting/sites/",
        views.posting_sites,
        name="posting_sites",
    ),
    path(
        "<uuid:pk>/posting/sites/new/",
        views.posting_site_add,
        name="posting_site_add",
    ),
    path(
        "<uuid:pk>/posting/sites/<uuid:site_pk>/edit/",
        views.posting_site_update,
        name="posting_site_update",
    ),
    path(
        "<uuid:pk>/posting/sites/<uuid:site_pk>/delete/",
        views.posting_site_delete,
        name="posting_site_delete",
    ),
    # P11: Approval workflow
    path(
        "<uuid:pk>/approval/cancel/",
        views.approval_cancel,
        name="approval_cancel",
    ),
    path(
        "approvals/",
        views.approval_queue,
        name="approval_queue",
    ),
    path(
        "approvals/<uuid:appr_pk>/decide/",
        views.approval_decide,
        name="approval_decide",
    ),
]
