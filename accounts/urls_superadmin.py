from django.urls import path

from . import views_superadmin

urlpatterns = [
    path("pending/", views_superadmin.pending_users_list, name="pending_users_list"),
    path("approve/<uuid:user_id>/", views_superadmin.approve_user, name="approve_user"),
]
