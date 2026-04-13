# accounts/urls_org.py
from django.urls import path

from . import views_org

urlpatterns = [
    path("", views_org.org_redirect, name="org_redirect"),
    path("info/", views_org.org_info, name="org_info"),
    path("members/", views_org.org_members, name="org_members"),
    path(
        "members/<uuid:pk>/approve/",
        views_org.org_member_approve,
        name="org_member_approve",
    ),
    path(
        "members/<uuid:pk>/reject/",
        views_org.org_member_reject,
        name="org_member_reject",
    ),
    path("members/<uuid:pk>/role/", views_org.org_member_role, name="org_member_role"),
    path(
        "members/<uuid:pk>/remove/",
        views_org.org_member_remove,
        name="org_member_remove",
    ),
    path("invites/", views_org.org_invites, name="org_invites"),
    path("invites/create/", views_org.org_invite_create, name="org_invite_create"),
    path(
        "invites/<uuid:pk>/deactivate/",
        views_org.org_invite_deactivate,
        name="org_invite_deactivate",
    ),
]
