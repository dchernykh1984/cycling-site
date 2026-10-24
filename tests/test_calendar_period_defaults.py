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
