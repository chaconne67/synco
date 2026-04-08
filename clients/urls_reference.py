from django.urls import path

from . import views_reference as views

app_name = "reference"

urlpatterns = [
    path("", views.reference_index, name="index"),
    # Universities
    path("universities/", views.reference_universities, name="universities"),
    path("universities/new/", views.university_create, name="university_create"),
    path(
        "universities/<uuid:pk>/edit/",
        views.university_update,
        name="university_update",
    ),
    path(
        "universities/<uuid:pk>/delete/",
        views.university_delete,
        name="university_delete",
    ),
    path("universities/import/", views.university_import, name="university_import"),
    path("universities/export/", views.university_export, name="university_export"),
    # Companies
    path("companies/", views.reference_companies, name="companies"),
    path("companies/new/", views.company_create, name="company_create"),
    path(
        "companies/<uuid:pk>/edit/",
        views.company_update,
        name="company_update",
    ),
    path(
        "companies/<uuid:pk>/delete/",
        views.company_delete,
        name="company_delete",
    ),
    path("companies/autofill/", views.company_autofill, name="company_autofill"),
    path("companies/import/", views.company_import, name="company_import"),
    path("companies/export/", views.company_export, name="company_export"),
    # Certs
    path("certs/", views.reference_certs, name="certs"),
    path("certs/new/", views.cert_create, name="cert_create"),
    path("certs/<uuid:pk>/edit/", views.cert_update, name="cert_update"),
    path("certs/<uuid:pk>/delete/", views.cert_delete, name="cert_delete"),
    path("certs/import/", views.cert_import, name="cert_import"),
    path("certs/export/", views.cert_export, name="cert_export"),
]
