"""E2E tests for the multi-select direction/discipline and event-type filters (issue #108).

Direction (dd-btn-1/menu-1) and Discipline (dd-btn-2/menu-2) form a 2-level cascade;
Event type (et-btn-1/menu-1) is a single-level dropdown. Each level is a Bootstrap
dropdown of checkboxes with a master "All" checkbox; the discipline level merges the
disciplines of every selected direction. Selecting a checkbox auto-submits the list
form (each filter's ids as one comma-joined ?param= value) and refetches the calendar.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import AROUND_UPCOMING, UPCOMING, open_filter_panel

# Built from the day the suite runs, like the events below it (conftest.UPCOMING).
_DATES = AROUND_UPCOMING


def _make_comp(organizer, title, discipline=None, event_type=None):
    comp = Competition.objects.create(
        title_ru=title,
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    if discipline is not None:
        comp.disciplines.set([discipline])
    if event_type is not None:
        comp.event_types.set([event_type])


# --------------------------------------------------------------------------- #
# Direction -> Discipline cascade
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
def test_direction_dropdown_lists_categories_on_calendar(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    page.click("#dd-btn-1")
    expect(page.locator(f"#dd-menu-1 input[value='{road_category.pk}']")).to_have_count(1)
    expect(page.locator(f"#dd-menu-1 input[value='{mtb_category.pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_discipline_dropdown_disabled_before_direction_chosen(page: Page, live_server, road_category, road_discipline):
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    expect(page.locator("#dd-btn-2")).to_be_disabled()


@pytest.mark.django_db(transaction=True)
def test_selecting_direction_populates_matching_disciplines(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    page.click("#dd-btn-1")
    page.check(f"#dd-menu-1 input[value='{road_category.pk}']")
    expect(page.locator("#dd-btn-2")).not_to_be_disabled()
    expect(page.locator(f"#dd-menu-2 input[value='{road_discipline.pk}']")).to_have_count(1)
    expect(page.locator(f"#dd-menu-2 input[value='{mtb_discipline.pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_multiselect_two_directions_merges_disciplines(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    page.click("#dd-btn-1")
    page.check(f"#dd-menu-1 input[value='{road_category.pk}']")
    page.check(f"#dd-menu-1 input[value='{mtb_category.pk}']")
    expect(page.locator(f"#dd-menu-2 input[value='{road_discipline.pk}']")).to_have_count(1)
    expect(page.locator(f"#dd-menu-2 input[value='{mtb_discipline.pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_direction_auto_submits_on_list(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    page.goto(f"{live_server.url}/calendar/list/")
    page.click("#dd-btn-1")
    with page.expect_navigation():
        page.check(f"#dd-menu-1 input[value='{road_category.pk}']")
    assert f"discipline_category={road_category.pk}" in page.url
    # After reload the discipline dropdown is restored to the chosen direction.
    expect(page.locator(f"#dd-menu-2 input[value='{road_discipline.pk}']")).to_have_count(1)
    expect(page.locator(f"#dd-menu-2 input[value='{mtb_discipline.pk}']")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_list_filters_by_single_direction(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category, mtb_discipline
):
    _make_comp(organizer, "Road Race Event", discipline=road_discipline)
    _make_comp(organizer, "MTB Race Event", discipline=mtb_discipline)
    page.goto(f"{live_server.url}/calendar/list/?discipline_category={road_category.pk}&{_DATES}")
    expect(page.locator("body")).to_contain_text("Road Race Event")
    expect(page.locator("body")).not_to_contain_text("MTB Race Event")


@pytest.mark.django_db(transaction=True)
def test_list_multiselect_two_directions_shows_both(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category, mtb_discipline
):
    _make_comp(organizer, "Road Race Event", discipline=road_discipline)
    _make_comp(organizer, "MTB Race Event", discipline=mtb_discipline)
    url = (
        f"{live_server.url}/calendar/list/"
        f"?discipline_category={road_category.pk}&discipline_category={mtb_category.pk}&{_DATES}"
    )
    page.goto(url)
    expect(page.locator("body")).to_contain_text("Road Race Event")
    expect(page.locator("body")).to_contain_text("MTB Race Event")


@pytest.mark.django_db(transaction=True)
def test_discipline_level_filter_on_list(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category, mtb_discipline
):
    _make_comp(organizer, "Road Race Event", discipline=road_discipline)
    _make_comp(organizer, "MTB Race Event", discipline=mtb_discipline)
    page.goto(f"{live_server.url}/calendar/list/?discipline={road_discipline.pk}&{_DATES}")
    expect(page.locator("body")).to_contain_text("Road Race Event")
    expect(page.locator("body")).not_to_contain_text("MTB Race Event")
    # The discipline checkbox is restored as checked.
    expect(page.locator(f"#dd-menu-2 input[value='{road_discipline.pk}']")).to_be_checked()


@pytest.mark.django_db(transaction=True)
def test_second_direction_survives_after_drilling_into_a_disciplines(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category, mtb_discipline
):
    # Regression: pick Road -> drill into the Road discipline -> then add the whole MTB direction.
    # MTB must stay checked after the auto-submit (the deepest-level emit used to drop it).
    _make_comp(organizer, "Road Race Event", discipline=road_discipline)
    _make_comp(organizer, "MTB Race Event", discipline=mtb_discipline)
    page.goto(f"{live_server.url}/calendar/list/?{_DATES}")

    page.click("#dd-btn-1")
    with page.expect_navigation():
        page.check(f"#dd-menu-1 input[value='{road_category.pk}']")
    page.click("#dd-btn-2")
    with page.expect_navigation():
        page.check(f"#dd-menu-2 input[value='{road_discipline.pk}']")
    page.click("#dd-btn-1")
    with page.expect_navigation():
        page.check(f"#dd-menu-1 input[value='{mtb_category.pk}']")

    # Both directions stay checked, and the drilled discipline too. Assert on the checkboxes
    # directly: to_be_checked() does not need the dropdown open, which avoids the open menu
    # overlapping the other (stacked) dropdown button on narrow/mobile viewports.
    expect(page.locator(f"#dd-menu-1 input[value='{road_category.pk}']")).to_be_checked()
    expect(page.locator(f"#dd-menu-1 input[value='{mtb_category.pk}']")).to_be_checked()
    expect(page.locator(f"#dd-menu-2 input[value='{road_discipline.pk}']")).to_be_checked()
    # OR semantics: the Road discipline event and the whole-MTB event are both listed.
    expect(page.locator("body")).to_contain_text("Road Race Event")
    expect(page.locator("body")).to_contain_text("MTB Race Event")


# --------------------------------------------------------------------------- #
# Event type
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
def test_event_type_dropdown_has_checkbox_options(page: Page, live_server, race_event_type, training_event_type):
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    page.click("#et-btn-1")
    expect(page.locator(f"#et-menu-1 input[value='{race_event_type.pk}']")).to_have_count(1)
    expect(page.locator(f"#et-menu-1 input[value='{training_event_type.pk}']")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_event_type_auto_submits_on_list(page: Page, live_server, race_event_type):
    page.goto(f"{live_server.url}/calendar/list/")
    page.click("#et-btn-1")
    with page.expect_navigation():
        page.check(f"#et-menu-1 input[value='{race_event_type.pk}']")
    assert f"event_type={race_event_type.pk}" in page.url


@pytest.mark.django_db(transaction=True)
def test_event_type_checkbox_restored_from_url(page: Page, live_server, race_event_type):
    page.goto(f"{live_server.url}/calendar/list/?event_type={race_event_type.pk}")
    page.click("#et-btn-1")
    expect(page.locator(f"#et-menu-1 input[value='{race_event_type.pk}']")).to_be_checked()


@pytest.mark.django_db(transaction=True)
def test_event_type_filters_list(page: Page, live_server, organizer, race_event_type, training_event_type):
    _make_comp(organizer, "Race Event", event_type=race_event_type)
    _make_comp(organizer, "Training Event", event_type=training_event_type)
    page.goto(f"{live_server.url}/calendar/list/?event_type={race_event_type.pk}&{_DATES}")
    expect(page.locator("body")).to_contain_text("Race Event")
    expect(page.locator("body")).not_to_contain_text("Training Event")


@pytest.mark.django_db(transaction=True)
def test_event_type_master_checkbox_selects_all(page: Page, live_server, race_event_type, training_event_type):
    page.goto(f"{live_server.url}/calendar/list/")
    page.click("#et-btn-1")
    with page.expect_navigation():
        page.check("#et-menu-1 input.mf-all")
    # One comma-joined value per filter, not one parameter per id (see test_filter_url_length.py).
    selected = set(parse_qs(urlsplit(page.url).query)["event_type"][0].split(","))
    assert selected == {str(race_event_type.pk), str(training_event_type.pk)}


# --------------------------------------------------------------------------- #
# Type-to-filter search box (shared with the location filter)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
def test_direction_search_filters_checkboxes(
    page: Page, live_server, road_category, road_discipline, mtb_category, mtb_discipline
):
    page.goto(f"{live_server.url}/calendar/")
    open_filter_panel(page)
    page.click("#dd-btn-1")
    road = page.locator(f"#dd-menu-1 li.mf-item-row:has(input[value='{road_category.pk}'])")
    mtb = page.locator(f"#dd-menu-1 li.mf-item-row:has(input[value='{mtb_category.pk}'])")
    expect(road).to_be_visible()
    expect(mtb).to_be_visible()
    page.fill("#dd-menu-1 .mf-search", "mtb")  # case-insensitive
    expect(mtb).to_be_visible()
    expect(road).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_event_type_search_filters_checkboxes(page: Page, live_server, race_event_type, training_event_type):
    page.goto(f"{live_server.url}/calendar/list/")
    open_filter_panel(page)
    page.click("#et-btn-1")
    race = page.locator(f"#et-menu-1 li.mf-item-row:has(input[value='{race_event_type.pk}'])")
    training = page.locator(f"#et-menu-1 li.mf-item-row:has(input[value='{training_event_type.pk}'])")
    expect(race).to_be_visible()
    expect(training).to_be_visible()
    page.fill("#et-menu-1 .mf-search", "train")  # case-insensitive
    expect(training).to_be_visible()
    expect(race).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_search_box_present_on_all_three_calendar_tabs(page: Page, live_server, race_event_type, training_event_type):
    for path in ("/calendar/", "/calendar/list/", "/calendar/map/"):
        page.goto(f"{live_server.url}{path}")
        open_filter_panel(page)
        page.click("#et-btn-1")
        expect(page.locator("#et-menu-1 .mf-search")).to_have_count(1)
