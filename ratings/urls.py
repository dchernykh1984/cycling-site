from django.urls import path

from ratings import views

app_name = "ratings"

urlpatterns = [
    path("", views.RatingsView.as_view(), name="index"),
    path("events/<int:pk>/review/", views.ReviewView.as_view(), name="review"),
    path("events/<int:pk>/summary/", views.SummaryView.as_view(), name="summary"),
]
