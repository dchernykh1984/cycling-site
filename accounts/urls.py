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
    path("hints/<str:key>/dismiss/", views.DismissHintView.as_view(), name="account_dismiss_hint"),
    path("preferences/filters/", views.SaveFilterPreferencesView.as_view(), name="account_save_filters"),
    path("managing/join/<uuid:key>/", views.JoinManagerView.as_view(), name="account_managing_join"),
    path("managing/invite/", views.ManagingActionView.as_view(action="issue"), name="account_managing_issue"),
    path("managing/invite/delete/", views.ManagingActionView.as_view(action="delete"), name="account_managing_delete"),
    path(
        "managing/waiting/<int:person_id>/accept/",
        views.ManagingActionView.as_view(action="accept"),
        name="account_managing_accept",
    ),
    path(
        "managing/waiting/<int:person_id>/reject/",
        views.ManagingActionView.as_view(action="reject"),
        name="account_managing_reject",
    ),
    path(
        "managing/waiting/accept-all/",
        views.ManagingActionView.as_view(action="accept_all"),
        name="account_managing_accept_all",
    ),
    path(
        "managing/waiting/reject-all/",
        views.ManagingActionView.as_view(action="reject_all"),
        name="account_managing_reject_all",
    ),
    path(
        "managing/members/<int:person_id>/remove/",
        views.ManagingActionView.as_view(action="drop"),
        name="account_managing_drop",
    ),
    path(
        "managing/managers/<int:person_id>/remove/",
        views.ManagingActionView.as_view(action="leave"),
        name="account_managing_leave",
    ),
]
