from django.urls import path

from . import views

app_name = "registrations"

urlpatterns = [
    path("competitions/<int:pk>/register/", views.RegisterForCompetitionView.as_view(), name="register"),
    path("competitions/<int:pk>/participants/", views.ParticipantListView.as_view(), name="participant_list"),
    path("competitions/<int:pk>/participants/add/", views.ManualAddRegistrationView.as_view(), name="manual_add"),
    path("competitions/<int:pk>/participants/export/", views.ExportParticipantsCSVView.as_view(), name="export_csv"),
    path(
        "competitions/<int:pk>/participants/<int:reg_pk>/approve/",
        views.ApproveRegistrationView.as_view(),
        name="approve",
    ),
    path(
        "competitions/<int:pk>/participants/<int:reg_pk>/reject/", views.RejectRegistrationView.as_view(), name="reject"
    ),
    path("competitions/<int:pk>/participants/<int:reg_pk>/mark-paid/", views.MarkPaidView.as_view(), name="mark_paid"),
    path(
        "competitions/<int:pk>/participants/<int:reg_pk>/edit/",
        views.EditRegistrationView.as_view(),
        name="edit_registration",
    ),
    path(
        "competitions/<int:pk>/participants/<int:reg_pk>/delete/",
        views.DeleteRegistrationView.as_view(),
        name="delete_registration",
    ),
    path("api/teams/autocomplete/", views.TeamAutocompleteView.as_view(), name="team_autocomplete"),
    path("api/cities/autocomplete/", views.CityAutocompleteView.as_view(), name="city_autocomplete"),
]
