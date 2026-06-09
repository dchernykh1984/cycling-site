from django.urls import path

from home.views import HomeEditView

urlpatterns = [
    path("home/edit/", HomeEditView.as_view(), name="home_edit"),
]
