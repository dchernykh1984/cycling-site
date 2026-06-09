"""E2E tests for direction/discipline cascade dropdowns on calendar and list pages."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import open_filter_panel


@pytest.mark.django_db(transaction=True)
def test_direction_dropdown_filters_disciplines_on_calendar(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    """Selecting a direction shows only matching disciplines in the discipline dropdown."""
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    expect(page.locator("#filter-discipline")).to_be_visible()

    page.select_option("#filter-direction", str(road_category.pk))

    # After selecting road: empty option + road discipline only
    expect(page.locator("#filter-discipline option")).to_have_count(2)
    expect(page.locator(f"#filter-discipline option[value='{road_discipline.pk}']")).to_have_count(1)
    expect(page.locator(f"#filter-discipline option[value='{mtb_discipline.pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_direction_dropdown_switch_shows_other_category_disciplines(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    """Switching direction updates the discipline dropdown to the new category."""
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)

    page.select_option("#filter-direction", str(road_category.pk))
    expect(page.locator(f"#filter-discipline option[value='{mtb_discipline.pk}']")).to_have_count(0)

    page.select_option("#filter-direction", str(mtb_category.pk))
    expect(page.locator(f"#filter-discipline option[value='{mtb_discipline.pk}']")).to_have_count(1)
    expect(page.locator(f"#filter-discipline option[value='{road_discipline.pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_direction_dropdown_reset_shows_all_disciplines(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    """Resetting direction to empty shows all disciplines again."""
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)

    page.select_option("#filter-direction", str(road_category.pk))
    expect(page.locator("#filter-discipline option")).to_have_count(2)

    page.select_option("#filter-direction", "")
    # empty option + road + mtb
    expect(page.locator("#filter-discipline option")).to_have_count(3)


@pytest.mark.django_db(transaction=True)
def test_direction_filter_on_list_page_auto_submits(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    """Selecting a direction on the list page auto-submits the form and updates the URL."""
    page.goto(f"{live_server.url}/calendar/list/")

    with page.expect_navigation():
        page.select_option("#filter-direction", str(road_category.pk))

    assert f"discipline_category={road_category.pk}" in page.url
    # After reload: discipline dropdown filtered to road only
    expect(page.locator(f"#filter-discipline option[value='{road_discipline.pk}']")).to_have_count(1)
    expect(page.locator(f"#filter-discipline option[value='{mtb_discipline.pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_list_page_shows_competition_when_direction_matches(
    page: Page, live_server, organizer, road_category, road_discipline
):
    """List page shows competitions whose discipline belongs to the selected direction."""
    Competition.objects.create(
        title_ru="Road Race Event",
        date_start=datetime.date(2026, 9, 15),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        discipline=road_discipline,
    )
    url = (
        f"{live_server.url}/calendar/list/"
        f"?discipline_category={road_category.pk}"
        f"&date_from=2026-09-01&date_to=2026-09-30"
    )
    page.goto(url)
    expect(page.locator("body")).to_contain_text("Road Race Event")


@pytest.mark.django_db(transaction=True)
def test_list_page_hides_competition_when_direction_differs(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category
):
    """List page hides competitions whose discipline does not belong to the selected direction."""
    Competition.objects.create(
        title_ru="Road Race Event",
        date_start=datetime.date(2026, 9, 15),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        discipline=road_discipline,
    )
    url = (
        f"{live_server.url}/calendar/list/"
        f"?discipline_category={mtb_category.pk}"
        f"&date_from=2026-09-01&date_to=2026-09-30"
    )
    page.goto(url)
    expect(page.locator("body")).not_to_contain_text("Road Race Event")
