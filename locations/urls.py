from django.urls import path

from locations import views

urlpatterns = [
    path("<int:pk>/delete/", views.LocationDeleteView.as_view(), name="location_delete"),
    path("<int:pk>/hide/", views.LocationHideView.as_view(), name="location_hide"),
]
