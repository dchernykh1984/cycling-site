from django.urls import path

from . import views

urlpatterns = [
    path("", views.CalendarView.as_view(), name="calendar"),
    path("list/", views.CompetitionListView.as_view(), name="calendar_list"),
    path("events/", views.CalendarEventsAPIView.as_view(), name="calendar_events_api"),
    path("submit/", views.SubmitCompetitionView.as_view(), name="calendar_submit"),
    path("moderate/", views.ModerationView.as_view(), name="calendar_moderate"),
    path("<int:pk>/", views.CompetitionDetailView.as_view(), name="competition_detail"),
    path("<int:pk>/approve/", views.ApproveCompetitionView.as_view(), name="competition_approve"),
    path("<int:pk>/reject/", views.RejectCompetitionView.as_view(), name="competition_reject"),
    path("<int:pk>/edit/", views.EditCompetitionView.as_view(), name="competition_edit"),
    path("<int:pk>/delete/", views.CompetitionDeleteView.as_view(), name="competition_delete"),
    path("<int:pk>/hide/", views.CompetitionHideView.as_view(), name="competition_hide"),
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
