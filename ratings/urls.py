from django.urls import path

from ratings import views

app_name = "ratings"

urlpatterns = [
    path("events/<int:pk>/review/", views.ReviewView.as_view(), name="review"),
]
