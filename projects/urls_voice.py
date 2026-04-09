from django.urls import path

from . import views_voice

urlpatterns = [
    path("transcribe/", views_voice.voice_transcribe, name="voice_transcribe"),
    path("intent/", views_voice.voice_intent, name="voice_intent"),
    path("preview/", views_voice.voice_preview, name="voice_preview"),
    path("confirm/", views_voice.voice_confirm, name="voice_confirm"),
    path("context/", views_voice.voice_context, name="voice_context"),
    path("history/", views_voice.voice_history, name="voice_history"),
    path("reset/", views_voice.voice_reset, name="voice_reset"),  # Amendment A4
    path(
        "meeting-upload/", views_voice.voice_meeting_upload, name="voice_meeting_upload"
    ),
    path(
        "meeting-status/<uuid:pk>/",
        views_voice.voice_meeting_status,
        name="voice_meeting_status",
    ),
    path("meeting-apply/", views_voice.voice_meeting_apply, name="voice_meeting_apply"),
]
