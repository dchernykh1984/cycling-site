from django.urls import path

from event_photos import views

app_name = "event_photos"

urlpatterns = [
    path("<int:pk>/photos/", views.event_photos, name="event"),
    path("<int:pk>/photos/manage/", views.manage, name="manage"),
    path("<int:pk>/photos/manage/<int:album_pk>/", views.album_action, name="album_action"),
    path("<int:pk>/photos/<int:album_pk>/", views.album, name="album"),
    path("<int:pk>/photos/registration/<int:reg_pk>/", views.registration_album, name="registration"),
    path("<int:pk>/photos/registration/<int:reg_pk>/<int:photo_pk>/", views.decide, name="decide"),
    path("<int:pk>/photos/registration/<int:reg_pk>/undo/", views.undo, name="undo"),
    path("<int:pk>/photos/thumb/<int:photo_pk>/<str:digest>.jpg", views.thumb, name="thumb"),
]
