"""E2E tests for the coverage-links editor on the competition edit page.

The rows are added and dropped by hand-written JS that also keeps the formset's TOTAL_FORMS in
step; nothing but a browser exercises that. What matters here is that a row added in the page
survives a save and shows up as a button on the event, and that a row dropped before saving leaves
no trace -- the two ways the counter can be got wrong.
"""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import inject_session


def _goto_edit(page: Page, live_server, user, competition):
    inject_session(page, live_server, user)
    page.goto(f"{live_server.url}/calendar/{competition.pk}/edit/")


def _save(page: Page):
    """The navbar's language switcher is a submit button too -- take the edit form's own."""
    page.locator("form[enctype='multipart/form-data'] button[type='submit']").click()


def _fill_row(page: Page, index: int, name: str, url: str):
    page.locator(f"#id_materials-{index}-title").fill(name)
    page.locator(f"#id_materials-{index}-url").fill(url)


@pytest.mark.django_db(transaction=True)
def test_one_blank_row_is_waiting_on_the_edit_page(page: Page, live_server, organizer, kz_competition):
    _goto_edit(page, live_server, organizer, kz_competition)
    expect(page.locator("#materials-container .material-row")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_the_add_button_appends_a_row(page: Page, live_server, organizer, kz_competition):
    _goto_edit(page, live_server, organizer, kz_competition)
    page.locator("#add-material-btn").click()
    expect(page.locator("#materials-container .material-row")).to_have_count(2)
    expect(page.locator("#id_materials-TOTAL_FORMS")).to_have_value("2")


@pytest.mark.django_db(transaction=True)
def test_two_materials_added_in_the_page_reach_the_event(page: Page, live_server, organizer, kz_competition):
    _goto_edit(page, live_server, organizer, kz_competition)
    _fill_row(page, 0, "Photos", "https://photos.example/album")
    page.locator("#add-material-btn").click()
    _fill_row(page, 1, "Video", "https://video.example/clip")
    _save(page)
    page.wait_for_url(f"{live_server.url}/calendar/{kz_competition.pk}/")
    expect(page.get_by_role("link", name="Photos")).to_have_attribute("href", "https://photos.example/album")
    expect(page.get_by_role("link", name="Video")).to_have_attribute("href", "https://video.example/clip")


@pytest.mark.django_db(transaction=True)
def test_a_row_dropped_before_saving_leaves_nothing_behind(page: Page, live_server, organizer, kz_competition):
    """The counter is not rewound when a row goes, so the gap it leaves must still save cleanly."""
    _goto_edit(page, live_server, organizer, kz_competition)
    page.locator("#add-material-btn").click()
    page.locator("#add-material-btn").click()
    _fill_row(page, 0, "Photos", "https://photos.example/album")
    _fill_row(page, 1, "Mistake", "https://example.com/mistake")
    _fill_row(page, 2, "Video", "https://video.example/clip")
    page.locator("#materials-container .material-row").nth(1).locator(".clear-material-btn").click()
    _save(page)
    page.wait_for_url(f"{live_server.url}/calendar/{kz_competition.pk}/")
    expect(page.get_by_role("link", name="Photos")).to_be_visible()
    expect(page.get_by_role("link", name="Video")).to_be_visible()
    expect(page.get_by_role("link", name="Mistake")).to_have_count(0)
