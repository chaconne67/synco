from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", views.login_page, name="login"),
    path("accounts/kakao/login/", views.kakao_login, name="kakao_login"),
    path("accounts/kakao/callback/", views.kakao_callback, name="kakao_callback"),
    path("accounts/role-select/", views.role_select, name="role_select"),
    path("accounts/settings/", views.settings_page, name="settings"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path(
        "accounts/dashboard/tasks-all/",
        views.dashboard_tasks_all,
        name="dashboard_tasks_all",
    ),
    path(
        "accounts/dashboard/tasks-overdue/",
        views.dashboard_tasks_overdue,
        name="dashboard_tasks_overdue",
    ),
]
