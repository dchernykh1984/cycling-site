from django.urls import path

from news import views

urlpatterns = [
    path("", views.NewsListView.as_view(), name="news_index"),
    path("articles/create/", views.NewsArticleCreateView.as_view(), name="news_article_create"),
    path("articles/<int:pk>/", views.NewsArticleDetailView.as_view(), name="news_article_detail"),
    path("articles/<int:pk>/edit/", views.NewsArticleEditView.as_view(), name="news_article_edit"),
    path("articles/<int:pk>/delete/", views.NewsArticleDeleteView.as_view(), name="news_article_delete"),
    path("articles/<int:pk>/hide/", views.NewsArticleHideView.as_view(), name="news_article_hide"),
    path("submit/", views.SubmitNewsView.as_view(), name="news_submit"),
    path("<int:page_pk>/comment/", views.AddCommentView.as_view(), name="news_add_comment"),
    path("comment/<int:pk>/delete/", views.DeleteCommentView.as_view(), name="news_delete_comment"),
]
