from django.urls import path

from . import views_news

app_name = "news"

urlpatterns = [
    path("", views_news.news_feed, name="news_feed"),
    path("filter/", views_news.news_filter, name="news_filter"),
    path("sources/", views_news.news_sources, name="news_sources"),
    path("sources/new/", views_news.news_source_create, name="news_source_create"),
    path("sources/<uuid:pk>/edit/", views_news.news_source_update, name="news_source_update"),
    path("sources/<uuid:pk>/delete/", views_news.news_source_delete, name="news_source_delete"),
    path("sources/<uuid:pk>/toggle/", views_news.news_source_toggle, name="news_source_toggle"),
]
