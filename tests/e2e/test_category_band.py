"""The category heading on a phone: a band, not a line lost between the cards.

Stacked into cards, every participant row has a border; the heading that introduced them had
none, so the one element meant to stand out was the lightest thing on the screen. It is now a
solid inverted band that sticks under the navbar, which also answers the question you cannot
answer ten cards down: which category am I reading?
"""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from registrations.models import CompetitionRegistration, RegistrationCategory
from tests.e2e.conftest import UPCOMING, inject_session

PHONE = {"width": 390, "height": 844}
NARROW = {"width": 320, "height": 568}


def _competition_with_two_categories(organizer):
    comp = Competition.objects.create(
        title_ru="Band RU",
        title_en="Band",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.FREE,
    )
    for name in ("Women", "Men"):
        category = RegistrationCategory.objects.create(competition=comp, name=name)
        for row in range(3):
            CompetitionRegistration.objects.create(
                competition=comp,
                category=category,
                first_name=f"{name}{row}",
                last_name="Rider",
                city="Almaty",
                birth_date=datetime.date(1990, 1, 1),
                gender="F" if name == "Women" else "M",
            )
    return comp


def _open(page, live_server, organizer, comp, theme, viewport=PHONE):
    page.set_viewport_size(viewport)
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/competitions/{comp.pk}/participants/")
    page.evaluate("theme => document.documentElement.setAttribute('data-bs-theme', theme)", theme)
    return page.locator(".participant-category").first


def _rgb(page, locator, prop):
    return locator.evaluate(f"el => getComputedStyle(el).{prop}")


def _luminance(colour):
    """Rough perceived lightness of an "rgb(r, g, b)" string, 0..255."""
    parts = [int(n) for n in colour.replace("rgba", "rgb").split("(")[1].split(")")[0].split(",")[:3]]
    return 0.299 * parts[0] + 0.587 * parts[1] + 0.114 * parts[2]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_band_is_filled_and_legible_in_both_themes(page: Page, live_server, organizer, theme):
    """Inverted against the page, whichever way round the page happens to be."""
    comp = _competition_with_two_categories(organizer)
    band = _open(page, live_server, organizer, comp, theme)
    expect(band).to_be_visible()

    background = _rgb(page, band, "backgroundColor")
    text = _rgb(page, band, "color")
    page_background = page.evaluate("() => getComputedStyle(document.body).backgroundColor")

    assert "rgba(0, 0, 0, 0)" not in background, f"the band has no fill in the {theme} theme"
    # The band must read against the page, and its own text against the band.
    assert abs(_luminance(background) - _luminance(page_background)) > 90, (
        f"band {background} is too close to the page {page_background} in the {theme} theme"
    )
    assert abs(_luminance(background) - _luminance(text)) > 90, (
        f"band text {text} is too close to its own fill {background} in the {theme} theme"
    )


@pytest.mark.django_db(transaction=True)
def test_the_band_sticks_below_the_navbar_rather_than_under_it(page: Page, live_server, organizer):
    """The navbar is sticky too, so a band pinned to 0 would be hidden behind it."""
    comp = _competition_with_two_categories(organizer)
    band = _open(page, live_server, organizer, comp, "dark")
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(200)

    navbar_bottom = page.evaluate("() => document.querySelector('nav.navbar').getBoundingClientRect().bottom")
    band_top = band.evaluate("el => el.getBoundingClientRect().top")
    assert band_top >= navbar_bottom - 1, (
        f"the band sits at {band_top}, above the navbar's bottom edge at {navbar_bottom}"
    )


@pytest.mark.django_db(transaction=True)
def test_the_offset_follows_the_navbar_when_it_grows(page: Page, live_server, organizer):
    """At the narrowest widths the brand wraps and the navbar gets taller; a constant would fail."""
    comp = _competition_with_two_categories(organizer)
    _open(page, live_server, organizer, comp, "dark", viewport=NARROW)
    page.wait_for_timeout(200)

    measured = page.evaluate("() => Math.round(document.querySelector('nav.navbar').getBoundingClientRect().height)")
    offset = page.evaluate(
        "() => getComputedStyle(document.documentElement).getPropertyValue('--ubt-sticky-top').trim()"
    )
    assert offset == f"{measured}px", f"offset {offset!r} does not match the navbar's {measured}px"


@pytest.mark.django_db(transaction=True)
def test_the_desktop_table_is_left_alone(page: Page, live_server, organizer):
    """The band is a phone fix; on a wide screen the table has its own column headings."""
    comp = _competition_with_two_categories(organizer)
    page.set_viewport_size({"width": 1200, "height": 900})
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/ru/competitions/{comp.pk}/participants/")
    position = page.locator(".participant-category").first.evaluate("el => getComputedStyle(el).position")
    assert position == "static", f"the band is {position} on the desktop layout"
