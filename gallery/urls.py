from django.urls import path

from gallery import views

urlpatterns = [
    path("", views.gallery_index, name="gallery_index"),
    path("events/", views.event_choices, name="gallery_event_choices"),
    path("albums/", views.gallery_albums, name="gallery_albums"),
    path("albums/new/", views.album_create, name="gallery_album_create"),
    path("albums/<int:pk>/", views.gallery_album, name="gallery_album"),
    path("albums/<int:pk>/edit/", views.album_edit, name="gallery_album_edit"),
    path("albums/<int:pk>/delete/", views.album_delete, name="gallery_album_delete"),
    path("photos/<int:pk>/", views.photo_detail, name="gallery_photo"),
    path("photos/<int:pk>/cover/", views.photo_set_cover, name="gallery_photo_cover"),
]
