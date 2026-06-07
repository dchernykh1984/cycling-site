from django.urls import path

from knowledge import views

urlpatterns = [
    path("submit/", views.SubmitArticleView.as_view(), name="knowledge_submit"),
]
