"""The event's useful links appear after the map and before its long announcement."""

from itertools import pairwise

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from calendar_app.models import CompetitionMaterial
from protocols.models import Protocol
from tests.language_urls import in_language


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_event_links_follow_the_start_point_before_the_announcement(
    page: Page, live_server, kz_competition, location_tree, language
):
    venue = location_tree["real"]
    venue.lat, venue.lng = "43.238949", "76.889709"
    venue.save()
    comp = kz_competition
    comp.location = venue
    comp.registration_enabled = True
    comp.url_registration = "https://example.com/register"
    document_names = ("route", "announcement", "regulations", "results")
    for name in document_names:
        setattr(comp, f"url_{name}", f"https://example.com/{name}")
    for locale in ("ru", "kk", "en"):
        setattr(comp, f"description_{locale}", "<p>Announcement body</p>" * 100)
    comp.save()
    protocol = Protocol.objects.create(competition=comp, protocol_type="absolute", is_live=True)
    CompetitionMaterial.objects.create(competition=comp, title="Photos", url="https://example.com/photos", order=0)
    CompetitionMaterial.objects.create(competition=comp, title="Video", url="https://example.com/video", order=1)

    page.goto(f"{live_server.url}/{language}/calendar/{comp.pk}/")
    selectors = [
        "#competition-map",
        "[role='group']:has(#map-link-google)",
        f"a[href='{comp.url_registration}']",
        f"a[href='{in_language(reverse('registrations:register', args=[comp.pk]), language)}']",
        *[f"a[href='{getattr(comp, f'url_{name}')}']" for name in document_names],
        f"a[href='{in_language(reverse('protocol_detail', args=[protocol.pk]), language)}']",
        "a[href='https://example.com/photos']",
        "a[href='https://example.com/video']",
        ".competition-description",
    ]
    for selector in selectors:
        expect(page.locator(selector)).to_have_count(1)
        expect(page.locator(selector)).to_be_visible()
    # Check reading order as well as rendered positions: wrapped buttons must keep the same order
    # on Android/iOS as on desktop, with no CSS ordering or duplicate mobile-only blocks.
    for before, after in pairwise(selectors):
        assert page.evaluate(
            "([a, b]) => !!(document.querySelector(a).compareDocumentPosition(document.querySelector(b)) & 4)",
            [before, after],
        )
        first = page.locator(before).bounding_box()
        second = page.locator(after).bounding_box()
        assert first is not None and second is not None
        assert second["y"] >= first["y"] + first["height"] - 1 or (
            abs(second["y"] - first["y"]) <= 1 and second["x"] >= first["x"] + first["width"] - 1
        ), (before, after, first, second)
    # Scope overflow to the moved buttons; the shared navbar may itself be wider than a small
    # desktop viewport in some locales.
    viewport_width = page.evaluate("window.innerWidth")
    for selector in selectors[2:-1]:
        box = page.locator(selector).bounding_box()
        assert box is not None
        assert box["x"] >= -1 and box["x"] + box["width"] <= viewport_width + 1, (selector, box)
