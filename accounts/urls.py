from django.contrib.auth.decorators import login_required
from django.urls import path

from accounts import views

urlpatterns = [
    path("profile/", login_required(views.ProfileView.as_view()), name="account_profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="account_profile_edit"),
    path("theme/", views.ThemeUpdateView.as_view(), name="account_theme"),
    path("api-token/regenerate/", views.ApiTokenRegenerateView.as_view(), name="account_api_token_regenerate"),
    path("resend-confirmation/", views.ResendEmailConfirmationView.as_view(), name="account_resend_confirmation"),
    path("contact/", views.ContactOwnersView.as_view(), name="account_contact_owners"),
    path("role-request/", views.RequestRoleView.as_view(), name="account_request_role"),
]
