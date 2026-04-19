from django.urls import path

from . import views

app_name = "clients"

urlpatterns = [
    path("", views.client_list, name="client_list"),
    path("page/", views.client_list_page, name="client_list_page"),
    path("new/", views.client_create, name="client_create"),
    path("<uuid:pk>/", views.client_detail, name="client_detail"),
    path("<uuid:pk>/projects/", views.client_projects_panel, name="client_projects_panel"),
    path("<uuid:pk>/edit/", views.client_update, name="client_update"),
    path("<uuid:pk>/delete/", views.client_delete, name="client_delete"),
    # Contract inline CRUD
    path(
        "<uuid:pk>/contracts/new/",
        views.contract_create,
        name="contract_create",
    ),
    path(
        "<uuid:pk>/contracts/<uuid:contract_pk>/edit/",
        views.contract_update,
        name="contract_update",
    ),
    path(
        "<uuid:pk>/contracts/<uuid:contract_pk>/delete/",
        views.contract_delete,
        name="contract_delete",
    ),
]
