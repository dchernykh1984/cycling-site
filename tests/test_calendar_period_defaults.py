"""A floating month link remains a month after switching to the filtered list."""

import datetime

from django.test import TestCase
from django.utils import timezone

from calendar_app.models import Competition, EventType
from calendar_app.views import end_of_month


class ExplicitMonthTests(TestCase):
    def test_explicit_month_keeps_the_filtered_list_inside_this_month(self):
        event_type = EventType.objects.create(name_ru="Race")
        event = Competition.objects.create(
            title_ru="Later race",
            date_start=timezone.localdate() + datetime.timedelta(days=60),
            status=Competition.Status.APPROVED,
        )
        event.event_types.add(event_type)
        response = self.client.get("/en/calendar/list/", {"event_type": event_type.pk, "period": "month"})
        self.assertEqual(response.context["date_to"], end_of_month(timezone.localdate()))
        self.assertNotContains(response, "Later race")
        # A plain faceted landing page still keeps its documented open future window.
        response = self.client.get("/en/calendar/list/", {"event_type": event_type.pk})
        self.assertContains(response, "Later race")

    def test_explicit_dates_win_over_the_month_marker(self):
        response = self.client.get("/en/calendar/list/", {"period": "month", "date_to": "2027-12-31"})
        self.assertEqual(response.context["date_to"], datetime.date(2027, 12, 31))


class AllUpcomingTests(TestCase):
    """``?period=upcoming``: every day from today on, with no last one, filtered or not."""

    def setUp(self):
        self.later = Competition.objects.create(
            title_ru="Race next season",
            date_start=timezone.localdate() + datetime.timedelta(days=200),
            status=Competition.Status.APPROVED,
        )

    def test_the_list_runs_from_today_with_no_last_day(self):
        response = self.client.get("/en/calendar/list/", {"period": "upcoming"})
        self.assertEqual(response.context["date_from"], timezone.localdate())
        self.assertIsNone(response.context["date_to"])
        self.assertContains(response, "Race next season")
        # The form keeps asking for it, so a filter changed next does not end it.
        self.assertContains(response, 'name="period" id="filter-period" value="upcoming">')
        # Without it the plain list is this month, the form sends no period.
        response = self.client.get("/en/calendar/list/")
        self.assertNotContains(response, "Race next season")
        self.assertContains(response, 'name="period" id="filter-period" value="upcoming" disabled>')

    def test_a_last_day_given_still_wins(self):
        day = timezone.localdate() + datetime.timedelta(days=10)
        response = self.client.get("/en/calendar/list/", {"period": "upcoming", "date_to": day.isoformat()})
        self.assertEqual(response.context["date_to"], day)
        self.assertNotContains(response, "Race next season")

    def test_the_map_opens_with_no_last_day(self):
        response = self.client.get("/en/calendar/map/", {"period": "upcoming"})
        self.assertEqual(response.context["date_from"], timezone.localdate())
        self.assertIsNone(response.context["date_to"])
        self.assertEqual(self.client.get("/en/calendar/map/").context["date_to"], end_of_month(timezone.localdate()))
