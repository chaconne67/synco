from django.urls import path

from . import views

urlpatterns = [
    path("accounts/login/", views.landing_page, name="landing"),
    path("accounts/kakao/login/", views.kakao_login, name="kakao_login"),
    path("accounts/kakao/callback/", views.kakao_callback, name="kakao_callback"),
    path("accounts/pending/", views.pending_approval_page, name="pending_approval"),

    path("accounts/settings/", views.settings_page, name="settings"),
    path("accounts/settings/profile/", views.settings_profile, name="settings_profile"),
    path("accounts/settings/email/", views.settings_email, name="settings_email"),
    path(
        "accounts/settings/telegram/", views.settings_telegram, name="settings_telegram"
    ),
    path(
        "accounts/settings/notify/", views.settings_notify, name="settings_notify"
    ),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),

    path("accounts/email/connect/", views.email_connect, name="email_connect"),
    path("accounts/email/callback/", views.email_oauth_callback, name="email_callback"),
    path("accounts/email/settings/", views.email_settings, name="email_settings"),
    path("accounts/email/disconnect/", views.email_disconnect, name="email_disconnect"),
]
