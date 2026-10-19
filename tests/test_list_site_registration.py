"""The events list offers registration that runs on this site, not only an external link.

An event taking entries here has no registration URL to copy into the row -- the URL field is
for registration somewhere else -- so the row used to show nothing at all, and a reader scanning
the list had no idea they could sign up in one click.
"""

import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from calendar_app.models import Competition

LIST_URL = reverse("calendar_list")


def _event(title, **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": timezone.localdate() + datetime.timedelta(days=5),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _register_url(comp):
    return reverse("registrations:register", args=[comp.pk])


class ListSiteRegistrationTests(TestCase):
    def test_open_registration_here_is_linked_from_the_list(self):
        comp = _event("Signs up here", registration_enabled=True)
        self.assertContains(self.client.get(LIST_URL), f'href="{_register_url(comp)}"')

    def test_closed_registration_here_is_not_linked(self):
        comp = _event(
            "Closed here",
            registration_enabled=True,
            registration_deadline=timezone.now() - datetime.timedelta(days=1),
        )
        self.assertNotContains(self.client.get(LIST_URL), _register_url(comp))

    def test_a_full_event_is_not_linked(self):
        """ "Open" means the event would take the entry: a full one would not."""
        comp = _event("Full here", registration_enabled=True, max_participants=0)
        self.assertNotContains(self.client.get(LIST_URL), _register_url(comp))

    def test_registration_here_wins_over_an_external_link(self):
        """One Register button per row, and it is the one the organizer switched on."""
        comp = _event("Both", registration_enabled=True, url_registration="https://example.com/signup")
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{_register_url(comp)}"')
        self.assertNotContains(response, "https://example.com/signup")

    def test_an_external_link_is_still_offered(self):
        _event("Elsewhere", url_registration="https://example.com/signup")
        self.assertContains(self.client.get(LIST_URL), 'href="https://example.com/signup"')

    def test_rows_without_a_limit_cost_no_extra_queries(self):
        """Asking an event whether it is open must not become one query per row."""
        _event("First", registration_enabled=True)
        self.client.get(LIST_URL)  # warm the per-process caches
        with CaptureQueriesContext(connection) as one:
            self.client.get(LIST_URL)
        for i in range(5):
            _event(f"More {i}", registration_enabled=True)
        with CaptureQueriesContext(connection) as six:
            self.client.get(LIST_URL)
        self.assertEqual(len(six.captured_queries), len(one.captured_queries))
