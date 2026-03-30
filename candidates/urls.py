from django.urls import path

from . import views

app_name = "candidates"

urlpatterns = [
    path("review/", views.review_list, name="review_list"),
    path("review/<uuid:pk>/", views.review_detail, name="review_detail"),
    path("review/<uuid:pk>/confirm/", views.review_confirm, name="review_confirm"),
    path("review/<uuid:pk>/reject/", views.review_reject, name="review_reject"),
]
