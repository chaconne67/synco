from django.urls import path

from . import views

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
]
