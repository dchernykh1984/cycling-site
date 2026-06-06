from django.contrib.auth.decorators import login_required
from django.urls import path

from accounts import views

urlpatterns = [
    path("profile/", login_required(views.ProfileView.as_view()), name="account_profile"),
    path("theme/", views.ThemeUpdateView.as_view(), name="account_theme"),
]
