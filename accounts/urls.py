from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", views.login_page, name="login"),
    path("accounts/kakao/login/", views.kakao_login, name="kakao_login"),
    path("accounts/kakao/callback/", views.kakao_callback, name="kakao_callback"),
    path("accounts/settings/", views.settings_page, name="settings"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    # P18: Gmail integration
    path("accounts/email/connect/", views.email_connect, name="email_connect"),
    path("accounts/email/callback/", views.email_oauth_callback, name="email_callback"),
    path("accounts/email/settings/", views.email_settings, name="email_settings"),
    path("accounts/email/disconnect/", views.email_disconnect, name="email_disconnect"),
]
