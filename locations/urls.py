from django.urls import path

from locations import views

urlpatterns = [
    path("add/", views.LocationCreateView.as_view(), name="location_add"),
    path("<int:pk>/edit/", views.LocationEditView.as_view(), name="location_edit"),
    path("<int:pk>/delete/", views.LocationDeleteView.as_view(), name="location_delete"),
    path("<int:pk>/hide/", views.LocationHideView.as_view(), name="location_hide"),
    path("<int:pk>/approve/", views.LocationApproveView.as_view(), name="location_approve"),
    path("<int:pk>/reject/", views.LocationRejectView.as_view(), name="location_reject"),
]
