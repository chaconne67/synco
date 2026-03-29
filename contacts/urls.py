from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("", views.contact_list, name="list"),
    path("new/", views.contact_create, name="create"),
    path("search/", views.contact_search, name="search"),
    path("import/", views.contact_import, name="import"),
    path("import/sheets/", views.contact_import_sheets, name="import_sheets"),
    path("import/confirm/", views.contact_import_confirm, name="import_confirm"),
    path("delete-all/", views.contact_delete_all, name="delete_all"),
    path("<uuid:pk>/", views.contact_detail, name="detail"),
    path("<uuid:pk>/ai/", views.contact_ai_section, name="ai_section"),
    path("<uuid:pk>/edit/", views.contact_edit, name="edit"),
    path("<uuid:pk>/delete/", views.contact_delete, name="delete"),
    path(
        "<uuid:contact_pk>/interactions/",
        views.interaction_create,
        name="interaction_create",
    ),
    path(
        "<uuid:contact_pk>/interactions/<uuid:pk>/edit/",
        views.interaction_edit,
        name="interaction_edit",
    ),
    path(
        "<uuid:contact_pk>/interactions/<uuid:pk>/delete/",
        views.interaction_delete,
        name="interaction_delete",
    ),
    # Tasks
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<uuid:pk>/complete/", views.task_complete, name="task_complete"),
    path("tasks/<uuid:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<uuid:pk>/delete/", views.task_delete, name="task_delete"),
]
