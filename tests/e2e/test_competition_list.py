"""E2E tests for the competition list filter auto-submit behaviour."""

import re

import pytest
from playwright.sync_api import Page, expect


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
    with page.expect_navigation():
        page.locator("input[name=date_from]").fill("2026-09-01")
        page.locator("input[name=date_from]").dispatch_event("change")
    expect(page).to_have_url(re.compile(r"date_from=2026-09-01"))


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
    """The list table must never produce a horizontal scrollbar, even with all 10 columns
    filled with long titles / location names (table-layout: fixed)."""
    import datetime

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
            date_start=datetime.date(2026, 9, 1),
            status=Competition.Status.APPROVED,
            submitted_by=organizer,
            location=venue,
            url_announcement="https://example.com/info",
            url_registration="https://example.com/register",
        )

    page.set_viewport_size({"width": 760, "height": 900})
    page.goto(f"{live_server.url}/calendar/list/?date_from=2026-08-15&date_to=2026-09-15")
    expect(page.locator(".table-responsive")).to_be_visible()
    overflow = page.evaluate(
        "() => { const el = document.querySelector('.table-responsive'); return el.scrollWidth - el.clientWidth; }"
    )
    assert overflow <= 1, f"competition list table overflows horizontally by {overflow}px"
