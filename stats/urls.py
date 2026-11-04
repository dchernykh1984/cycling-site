from django.urls import path

from stats import views

app_name = "stats"

urlpatterns = [path("", views.dashboard, name="dashboard")]
