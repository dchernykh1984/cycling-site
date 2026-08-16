"""E2E tests for the competition list filter auto-submit behaviour."""

import re

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING


@pytest.mark.django_db(transaction=True)
def test_filter_form_has_no_apply_button(page: Page, live_server):
    """The 'Apply' button was removed; filters submit on change instead."""
    page.goto(f"{live_server.url}/calendar/list/")
    # There should be a Reset link but no submit/apply button inside the filter form
    filter_form = page.locator("#filter-form")
    expect(filter_form).to_be_visible()
    expect(filter_form.locator("button[type=submit]")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_date_filter_auto_submits(page: Page, live_server, approved_competition):
    """Changing the date_from input auto-submits and reflects the new value in the URL."""
    page.goto(f"{live_server.url}/calendar/list/")
    typed = f"{UPCOMING:%Y-%m-%d}"
    page.locator("input[name=date_from]").fill(typed)
    # The change handler auto-submits; on webkit the navigation it triggers can interrupt the
    # dispatch call itself ("Frame load interrupted"), which is harmless here. Auto-submit may also
    # fire more than one navigation. Ignore those and assert on the resulting URL instead.
    try:
        page.locator("input[name=date_from]").dispatch_event("change")
    except PlaywrightError:
        pass
    # Poll the current URL instead of wait_for_url: the latter tracks a single navigation event and
    # raises "Frame load interrupted" on webkit when the auto-submit fires a second navigation that
    # supersedes it. to_have_url re-reads page.url until it matches, so extra navigations are fine.
    expect(page).to_have_url(re.compile(f"date_from={typed}"), timeout=15000)


@pytest.mark.django_db(transaction=True)
def test_reset_link_clears_filters(page: Page, live_server):
    """The Reset link navigates to the plain list URL."""
    page.goto(f"{live_server.url}/calendar/list/?date_from=2026-01-01")
    # The Reset link lives inside the filter form (the header has a view switcher that
    # also points at the list URL), so scope the selector to the form.
    page.locator("#filter-form a[href*='calendar/list']").click()
    # After reset, no query params
    assert "date_from" not in page.url


@pytest.mark.django_db(transaction=True)
def test_list_table_fits_without_horizontal_scroll(page: Page, live_server, organizer):
    """At desktop/tablet width (above the mobile card breakpoint) the fixed-layout table must
    never produce a horizontal scrollbar, even with all 10 columns filled with long titles /
    location names."""

    from calendar_app.models import Competition
    from locations.models import Location

    long = "A fairly long placeholder name for layout testing"
    country = Location.add_root(name="Kazakhstan", name_ru="Kazakhstan", name_kk="Kazakhstan", name_en="Kazakhstan")
    region = country.add_child(
        name=f"{long} region", name_ru=f"{long} region", name_kk=f"{long} region", name_en=f"{long} region"
    )
    city = region.add_child(name=f"{long} city", name_ru=f"{long} city", name_kk=f"{long} city", name_en=f"{long} city")
    venue = city.add_child(
        name=f"{long} venue", name_ru=f"{long} venue", name_kk=f"{long} venue", name_en=f"{long} venue"
    )
    for i in range(6):
        Competition.objects.create(
            title_ru=f"{long} competition {i} 2026",
            title_en=f"{long} competition {i} 2026",
            date_start=UPCOMING,
            status=Competition.Status.APPROVED,
            submitted_by=organizer,
            location=venue,
            url_announcement="https://example.com/info",
            url_registration="https://example.com/register",
        )

    page.set_viewport_size({"width": 800, "height": 900})
    page.goto(f"{live_server.url}/calendar/list/?{AROUND_UPCOMING}")
    expect(page.locator(".table-responsive")).to_be_visible()
    overflow = page.evaluate(
        "() => { const el = document.querySelector('.table-responsive'); return el.scrollWidth - el.clientWidth; }"
    )
    assert overflow <= 1, f"competition list table overflows horizontally by {overflow}px"


@pytest.mark.django_db(transaction=True)
def test_list_table_stacks_into_cards_on_mobile(page: Page, live_server, approved_competition):
    """On a phone-width viewport the 10-column table would otherwise squash to one character
    per line, so below the md breakpoint each row renders as a stacked card: the header row is
    hidden, every cell carries a data-label, and the page has no horizontal scroll."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/calendar/list/?{AROUND_UPCOMING}")
    # The table still renders (one approved competition in range), but as stacked cards: the
    # header row is hidden and each cell exposes its column name via data-label.
    expect(page.locator(".calendar-list-table")).to_be_visible()
    expect(page.locator(".calendar-list-table thead")).to_be_hidden()
    expect(page.locator(".calendar-list-table td[data-label]").first).to_be_visible()
    # No horizontal scroll anywhere on the page.
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 1, f"mobile list page overflows horizontally by {overflow}px"
