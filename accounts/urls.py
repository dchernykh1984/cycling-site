from django.contrib.auth.decorators import login_required
from django.urls import path

from accounts import views

urlpatterns = [
    path("profile/", login_required(views.ProfileView.as_view()), name="account_profile"),
    path("privacy-consent/", views.PrivacyConsentView.as_view(), name="account_privacy_consent"),
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
    # People without accounts the member enters for starts (issue #438)
    path("virtual-members/consent/", views.VirtualMembersConsentView.as_view(), name="account_virtual_consent"),
    path("service-accounts/", views.ServiceAccountsView.as_view(), name="account_service_accounts"),
    path("virtual-members/add/", views.VirtualMemberAddView.as_view(), name="account_virtual_add"),
    path("virtual-members/<int:pk>/edit/", views.VirtualMemberEditView.as_view(), name="account_virtual_edit"),
    path("virtual-members/<int:pk>/delete/", views.VirtualMemberDeleteView.as_view(), name="account_virtual_delete"),
    path(
        "virtual-members/<int:pk>/transfer/",
        views.VirtualMemberTransferView.as_view(action="issue"),
        name="account_virtual_transfer",
    ),
    path(
        "virtual-members/<int:pk>/transfer/confirm/",
        views.VirtualMemberTransferView.as_view(action="confirm"),
        name="account_virtual_transfer_confirm",
    ),
    path(
        "virtual-members/<int:pk>/transfer/reject/",
        views.VirtualMemberTransferView.as_view(action="reject"),
        name="account_virtual_transfer_reject",
    ),
    path("virtual-members/take/<uuid:key>/", views.VirtualMemberClaimView.as_view(), name="account_virtual_claim"),
]
