from django.urls import path

from . import views
from .views_extension import (
    extension_auth_status,
    extension_check_duplicate,
    extension_save_profile,
    extension_search,
    extension_stats,
)

app_name = "candidates"

urlpatterns = [
    # Phase 2: Search UI
    path("", views.candidate_list, name="candidate_list"),
    path("<uuid:pk>/", views.candidate_detail, name="candidate_detail"),
    path("search/", views.search_chat, name="search_chat"),
    path("voice/", views.voice_transcribe, name="voice_transcribe"),
    path("chat-history/", views.chat_history, name="chat_history"),
    # Phase 1: Review UI
    path("review/", views.review_list, name="review_list"),
    path("review/<uuid:pk>/", views.review_detail, name="review_detail"),
    path("review/<uuid:pk>/confirm/", views.review_confirm, name="review_confirm"),
    path("review/<uuid:pk>/reject/", views.review_reject, name="review_reject"),
    # Comments
    path("<uuid:pk>/comments/", views.comment_create, name="comment_create"),
    # Extension API
    path("extension/auth-status/", extension_auth_status, name="extension_auth_status"),
    path(
        "extension/save-profile/", extension_save_profile, name="extension_save_profile"
    ),
    path(
        "extension/check-duplicate/",
        extension_check_duplicate,
        name="extension_check_duplicate",
    ),
    path("extension/search/", extension_search, name="extension_search"),
    path("extension/stats/", extension_stats, name="extension_stats"),
]
