"""`GET /api/v1/competitions/{id}/track`: the track an event's page draws, to whoever may read the event."""

import datetime
import shutil
import tempfile
import uuid

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition

GPX = (
    b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
    b'<trkpt lat="43.239" lon="76.8897"/><trkpt lat="43.26" lon="76.86"/></trkseg></trk></gpx>'
)


class RouteTrackApiTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        media_root = override_settings(MEDIA_ROOT=media)
        media_root.enable()
        self.addCleanup(media_root.disable)
        self.author = User.objects.create_user(
            username="author", email="author@example.com", password="pw", role=User.Role.ORGANIZER
        )
        self.author.api_token = uuid.uuid4()
        self.author.save(update_fields=["api_token"])

    def _event(self, route: bytes | None = GPX, **fields) -> Competition:
        defaults = {
            "title_ru": "Ride",
            "date_start": timezone.localdate() + datetime.timedelta(days=7),
            "status": Competition.Status.APPROVED,
            "submitted_by": self.author,
        }
        event = Competition.objects.create(**{**defaults, **fields})
        if route is not None:
            event.file_route.save("ride.gpx", ContentFile(route))
        return event

    def _get(self, event: Competition, user: User | None = None):
        headers = {"Authorization": f"Bearer {user.api_token}"} if user else {}
        return self.client.get(f"/api/v1/competitions/{event.pk}/track", headers=headers)

    def test_it_is_the_line_the_page_draws_as_geojson_with_the_file_it_came_from(self):
        event = self._event()
        response = self._get(event)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": [[[76.8897, 43.239], [76.86, 43.26]]]},
                "properties": {"file": f"http://testserver{event.file_route.url}"},
            },
        )

    def test_an_event_whose_route_draws_nothing_has_no_track(self):
        self.assertEqual(self._get(self._event(route=None)).status_code, 404)
        self.assertEqual(self._get(self._event(route=b"%PDF-1.7 a route map")).status_code, 404)

    def test_what_the_api_does_not_show_it_gives_no_track_of(self):
        pending = self._event(status=Competition.Status.PENDING_APPROVAL)
        hidden = self._event(is_hidden=True)
        for event in (pending, hidden):
            self.assertEqual(self._get(event).status_code, 404)
            self.assertEqual(self._get(event, self.author).status_code, 200)
