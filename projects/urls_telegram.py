from django.urls import path

from . import views_telegram

app_name = "telegram"

urlpatterns = [
    path("webhook/", views_telegram.telegram_webhook, name="webhook"),
    path("bind/", views_telegram.telegram_bind, name="bind"),
    path("unbind/", views_telegram.telegram_unbind, name="unbind"),
    path("test/", views_telegram.telegram_test_send, name="test"),
    path(
        "settings-partial/", views_telegram.telegram_bind_partial, name="bind_partial"
    ),
    path("test-partial/", views_telegram.telegram_test_partial, name="test_partial"),
    path(
        "unbind-partial/", views_telegram.telegram_unbind_partial, name="unbind_partial"
    ),
]
