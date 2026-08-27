from django.urls import path

from . import views
from .feeds import CompetitionICSView

urlpatterns = [
    path("", views.CalendarView.as_view(), name="calendar"),
    path("list/", views.CompetitionListView.as_view(), name="calendar_list"),
    path("calendar.ics", CompetitionICSView.as_view(), name="calendar_ics"),
    path("map/", views.CalendarMapView.as_view(), name="calendar_map"),
    path("events/", views.CalendarEventsAPIView.as_view(), name="calendar_events_api"),
    path("map/events/", views.CalendarMapAPIView.as_view(), name="calendar_map_api"),
    path("submit/", views.SubmitCompetitionView.as_view(), name="calendar_submit"),
    path("moderate/", views.ModerationView.as_view(), name="calendar_moderate"),
    path("<int:pk>/", views.CompetitionDetailView.as_view(), name="competition_detail"),
    path("<int:pk>/approve/", views.ApproveCompetitionView.as_view(), name="competition_approve"),
    path("<int:pk>/reject/", views.RejectCompetitionView.as_view(), name="competition_reject"),
    path("<int:pk>/edit/", views.EditCompetitionView.as_view(), name="competition_edit"),
    path("<int:pk>/delete/", views.CompetitionDeleteView.as_view(), name="competition_delete"),
    path("<int:pk>/resubmit/", views.ResubmitCompetitionView.as_view(), name="competition_resubmit"),
    path("<int:pk>/hide/", views.CompetitionHideView.as_view(), name="competition_hide"),
    path("<int:pk>/favorite/toggle/", views.ToggleFavoriteView.as_view(), name="competition_toggle_favorite"),
    path("<int:pk>/report/", views.ReportCompetitionView.as_view(), name="competition_report"),
    path("<int:pk>/report/dismiss/", views.DismissReportsView.as_view(), name="competition_dismiss_reports"),
    path(
        "<int:pk>/token/regenerate/",
        views.RegenerateUploadTokenView.as_view(),
        name="competition_regenerate_token",
    ),
    path("<int:pk>/token/delete/", views.DeleteUploadTokenView.as_view(), name="competition_delete_token"),
    path(
        "<int:competition_pk>/comments/add/",
        views.AddCompetitionCommentView.as_view(),
        name="competition_add_comment",
    ),
    path(
        "comments/<int:pk>/delete/",
        views.DeleteCompetitionCommentView.as_view(),
        name="competition_delete_comment",
    ),
]
