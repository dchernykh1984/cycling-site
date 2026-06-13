from django.urls import path

from knowledge import views

urlpatterns = [
    path("submit/", views.SubmitArticleView.as_view(), name="knowledge_submit"),
    path("add/", views.AddArticleView.as_view(), name="knowledge_add"),
    path("submissions/<int:pk>/", views.SubmissionDetailView.as_view(), name="knowledge_submission_detail"),
    path("submissions/<int:pk>/approve/", views.ApproveSubmissionView.as_view(), name="knowledge_submission_approve"),
    path("submissions/<int:pk>/reject/", views.RejectSubmissionView.as_view(), name="knowledge_submission_reject"),
    path("articles/<int:pk>/delete/", views.KnowledgeArticleDeleteView.as_view(), name="knowledge_article_delete"),
    path("articles/<int:pk>/hide/", views.KnowledgeArticleHideView.as_view(), name="knowledge_article_hide"),
]
