from django.urls import path

from . import views

urlpatterns = [
    path("", views.virtual_ride, name="virtual_ride"),
]
