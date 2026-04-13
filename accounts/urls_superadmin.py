from django.urls import path

from . import views_superadmin

urlpatterns = [
    path("companies/", views_superadmin.companies_page, name="superadmin_companies"),
]
