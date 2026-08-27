from django.urls import path

from news import views
from news.feeds import NewsAtomFeed, NewsFeed

urlpatterns = [
    path("", views.NewsListView.as_view(), name="news_index"),
    path("rss.xml", NewsFeed(), name="news_rss"),
    path("atom.xml", NewsAtomFeed(), name="news_atom"),
    path("articles/create/", views.NewsArticleCreateView.as_view(), name="news_article_create"),
    path("articles/<int:pk>/", views.NewsArticleDetailView.as_view(), name="news_article_detail"),
    path("articles/<int:pk>/edit/", views.NewsArticleEditView.as_view(), name="news_article_edit"),
    path("articles/<int:pk>/delete/", views.NewsArticleDeleteView.as_view(), name="news_article_delete"),
    path("articles/<int:pk>/hide/", views.NewsArticleHideView.as_view(), name="news_article_hide"),
    path("articles/<int:pk>/comment/", views.AddNewsArticleCommentView.as_view(), name="news_article_add_comment"),
    path(
        "articles/comment/<int:pk>/delete/",
        views.DeleteNewsArticleCommentView.as_view(),
        name="news_article_delete_comment",
    ),
    path("submit/", views.SubmitNewsView.as_view(), name="news_submit"),
    path("submissions/<int:pk>/", views.NewsSubmissionDetailView.as_view(), name="news_submission_detail"),
    path("submissions/<int:pk>/approve/", views.NewsSubmissionApproveView.as_view(), name="news_submission_approve"),
    path("submissions/<int:pk>/reject/", views.NewsSubmissionRejectView.as_view(), name="news_submission_reject"),
    path("<int:page_pk>/comment/", views.AddCommentView.as_view(), name="news_add_comment"),
    path("comment/<int:pk>/delete/", views.DeleteCommentView.as_view(), name="news_delete_comment"),
]
