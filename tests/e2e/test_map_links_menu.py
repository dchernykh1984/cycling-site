"""The event page offers its start point in the deployment's map services from one menu (#335)."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db(transaction=True)
def test_one_button_opens_every_map_service_each_big_enough_to_tap(
    page: Page, live_server, kz_competition, location_tree, settings
):
    settings.MAP_LINK_SERVICES = ["2gis", "yandex", "google", "apple", "osm"]
    venue = location_tree["real"]
    venue.lat, venue.lng = "43.238949", "76.889709"
    venue.save()
    kz_competition.location = venue
    kz_competition.save()
    page.set_viewport_size({"width": 360, "height": 740})

    page.goto(f"{live_server.url}/en/calendar/{kz_competition.pk}/")
    toggle = page.locator("#map-links-toggle")
    expect(toggle).to_have_text("Link to the start point")
    expect(page.locator("#map-link-2gis")).to_be_hidden()

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    items = page.locator("#map-links .dropdown-item")
    expect(items).to_have_count(5)
    for key in settings.MAP_LINK_SERVICES:
        item = page.locator(f"#map-link-{key}")
        expect(item).to_be_visible()
        expect(item).to_have_attribute("target", "_blank")
        box = item.bounding_box()
        assert box is not None and box["height"] >= 44 - 0.5, (key, box)
        assert box["x"] >= 0 and box["x"] + box["width"] <= 360, (key, box)
    toggle_box = toggle.bounding_box()
    assert toggle_box is not None and toggle_box["height"] >= 44 - 0.5, toggle_box
