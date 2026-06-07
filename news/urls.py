from django.urls import path

from news import views

urlpatterns = [
    path("submit/", views.SubmitNewsView.as_view(), name="news_submit"),
    path("<int:page_pk>/comment/", views.AddCommentView.as_view(), name="news_add_comment"),
    path("comment/<int:pk>/delete/", views.DeleteCommentView.as_view(), name="news_delete_comment"),
]
