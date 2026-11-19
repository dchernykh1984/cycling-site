from django.urls import path

from . import views

urlpatterns = [
    path("", views.virtual_ride, name="virtual_ride"),
    path("strava/connect/", views.strava_connect, name="virtual_ride_strava_connect"),
    path("strava/callback/", views.strava_callback, name="virtual_ride_strava_callback"),
    path("strava/disconnect/", views.strava_disconnect, name="virtual_ride_strava_disconnect"),
    path("services/<str:service>/send/", views.service_sending, name="virtual_ride_service_sending"),
    path("intervals/connect/", views.intervals_connect, name="virtual_ride_intervals_connect"),
    path("intervals/disconnect/", views.intervals_disconnect, name="virtual_ride_intervals_disconnect"),
]
