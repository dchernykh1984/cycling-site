from django.urls import path

from knowledge import views

urlpatterns = [
    path("submit/", views.SubmitArticleView.as_view(), name="knowledge_submit"),
    path("articles/<int:pk>/delete/", views.KnowledgeArticleDeleteView.as_view(), name="knowledge_article_delete"),
    path("articles/<int:pk>/hide/", views.KnowledgeArticleHideView.as_view(), name="knowledge_article_hide"),
]
