"""An event's page draws its route file's track on the map, the start with it when it has one."""

import datetime
import json
import re
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import translation
from django.utils.translation import gettext

from calendar_app.models import Competition
from locations.models import Location
from tests.language_urls import in_language

GPX = (
    b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
    b'<trkpt lat="43.239" lon="76.8897"/><trkpt lat="43.26" lon="76.86"/><trkpt lat="43.26" lon="76.91"/>'
    b"</trkseg></trk></gpx>"
)
TRACK = re.compile(r'<script id="competition-route-track" type="application/json">(.*?)</script>', re.S)


class _EventPage(TestCase):
    """An approved event at a venue with its own point, and its page."""

    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        media_root = override_settings(MEDIA_ROOT=media)
        media_root.enable()
        self.addCleanup(media_root.disable)
        country = Location.add_root(name_ru="KZ", name_en="KZ")
        region = country.add_child(name_ru="Almaty region", name_en="Almaty region")
        self.city = region.add_child(name_ru="Almaty", name_en="Almaty", lat="43.238949", lng="76.889709")
        self.venue = self.city.add_child(name_ru="Stele", name_en="Stele", lat="43.2390", lng="76.8897")
        self.competition = Competition.objects.create(
            title_ru="Ride",
            date_start=datetime.date(2026, 11, 7),
            status=Competition.Status.APPROVED,
            location=self.venue,
        )

    def _page(self) -> str:
        response = self.client.get(in_language(self.competition.get_absolute_url(), "en"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _with_track(self) -> None:
        self.competition.file_route.save("ride.gpx", ContentFile(GPX))


class RouteTrackPageTests(_EventPage):
    def test_the_page_carries_the_track_it_draws_and_says_what_the_arrows_mean(self):
        self._with_track()
        html = self._page()
        found = TRACK.search(html)
        self.assertIsNotNone(found)
        self.assertEqual(
            json.loads(found.group(1) if found else "null"),
            {"type": "MultiLineString", "coordinates": [[[76.8897, 43.239], [76.86, 43.26], [76.91, 43.26]]]},
        )
        self.assertIn("calendar_app/route_track.js", html)
        self.assertIn("Arrows show the direction of the track.", html)
        self.assertIn("drawRouteTrack(map, JSON.parse(track.textContent), start)", html)

    def test_a_city_s_point_is_no_start_so_the_map_opens_on_the_track_alone(self):
        self.competition.location = self.city.add_child(name_ru="Somewhere", name_en="Somewhere")
        self.competition.save()
        self._with_track()
        html = self._page()
        self.assertIn('id="competition-map"', html)
        self.assertIn("L.marker(start)", html)  # the city's pin is still drawn
        self.assertIn("drawRouteTrack(map, JSON.parse(track.textContent), null)", html)

    def test_an_event_with_no_place_still_draws_its_track(self):
        self.competition.location = None
        self.competition.save()
        self._with_track()
        html = self._page()
        self.assertIn('id="competition-map"', html)
        self.assertIn("leaflet.js", html)
        self.assertNotIn("L.marker(start)", html)
        self.assertIsNotNone(TRACK.search(html))

    def test_without_a_track_the_map_is_drawn_as_before(self):
        self.competition.file_route.save("route.pdf", ContentFile(b"%PDF-1.7 a route map"))
        html = self._page()
        self.assertIsNone(TRACK.search(html))
        self.assertNotIn("route_track.js", html)
        self.assertNotIn("Arrows show the direction of the track.", html)
        self.assertIn("L.marker(start)", html)


class RouteButtonsTests(_EventPage):
    """A route's link and its file are offered side by side, each when it is there."""

    def test_the_link_opens_the_track_and_the_file_downloads_it(self):
        self.competition.url_route = "https://example.com/route"
        self.competition.save()
        self._with_track()
        html = self._page()
        link = html.index('id="route-link"')
        download = html.index('id="route-download"')
        self.assertLess(link, download)
        self.assertIn('href="https://example.com/route" target="_blank"', html)
        self.assertIn(f'href="{self.competition.file_route.url}" download', html)
        self.assertIn("Link to the track</a>", html)
        self.assertIn("Download the track</a>", html)

    def test_each_button_comes_only_with_its_own_half(self):
        self.competition.url_route = "https://example.com/route"
        self.competition.save()
        self.assertIn('id="route-link"', self._page())
        self.assertNotIn('id="route-download"', self._page())
        self.competition.url_route = ""
        self.competition.save()
        self._with_track()
        self.assertNotIn('id="route-link"', self._page())
        self.assertIn('id="route-download"', self._page())

    def test_a_route_file_that_is_no_track_keeps_its_route_button(self):
        self.competition.file_route.save("route.pdf", ContentFile(b"%PDF-1.7 a route map"))
        html = self._page()
        self.assertIn(f'href="{self.competition.file_route.url}" target="_blank"', html)
        self.assertIn('id="route-file">Route</a>', html)
        self.assertNotIn('id="route-download"', html)

    def test_the_buttons_speak_the_page_s_language(self):
        self.competition.url_route = "https://example.com/route"
        self.competition.save()
        self._with_track()
        response = self.client.get(in_language(self.competition.get_absolute_url(), "kk"))
        with translation.override("kk"):
            words = [gettext("Link to the track"), gettext("Download the track")]
        self.assertNotIn("Link to the track", words)
        for word in words:
            self.assertContains(response, word)
