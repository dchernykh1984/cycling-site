from django.urls import path

from . import views

urlpatterns = [
    path(
        "api/protocols/<int:pk>/last_updated/",
        views.protocol_last_updated,
        name="protocol_last_updated",
    ),
    path("protocols/<int:pk>/html/", views.protocol_html, name="protocol_html"),
    path("protocols/<int:pk>/", views.protocol_detail, name="protocol_detail"),
]
