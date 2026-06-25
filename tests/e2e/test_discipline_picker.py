"""E2E tests for the direction -> discipline picker on the competition submit/edit forms.

The picker reuses the searchable multi-select cascade from the event filters: pick one or
more directions, then tick the disciplines that get attached to the competition. These run a
real browser because the selection is wired entirely in JavaScript (hidden inputs are built
on the fly), which Django template-level tests cannot exercise.
"""

import datetime

import pytest
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from calendar_app.models import Competition, Discipline, DisciplineCategory
from tests.e2e.conftest import inject_session, switch_locale


def _open(page: Page, btn: str, menu: str) -> None:
    # The dropdowns use data-bs-auto-close="outside", so several boxes can be ticked while the menu
    # stays open; only open it when it is not already showing. On the heavy submit page (Quill x3),
    # webkit can attach Bootstrap's dropdown handler a beat after load and drop the first toggle
    # click, so retry the toggle until the menu actually opens.
    menu_loc = page.locator(menu)
    for _ in range(5):
        if menu_loc.is_visible():
            return
        page.click(btn)
        try:
            menu_loc.wait_for(state="visible", timeout=2000)
            return
        except PlaywrightTimeoutError:
            continue
    menu_loc.wait_for(state="visible")


def _tick(page: Page, menu: str, value) -> None:
    # page.check() flakes on webkit on the heavy submit page: a checkbox nested in its <label> can
    # double-toggle (the click re-fires through the label) and end up unchanged. Click the box, and
    # if it didn't stick, click the row's text label, which toggles it exactly once.
    box = page.locator(f"{menu} input.mf-item[value='{value}']")
    expect(box).to_be_visible()
    if box.is_checked():
        return
    box.click()
    if not box.is_checked():
        page.locator(f"{menu} li.mf-item-row:has(input.mf-item[value='{value}']) span").click()
    expect(box).to_be_checked()


def _pick_direction(page: Page, value) -> None:
    _open(page, "#disc-dd-btn-1", "#disc-dd-menu-1")
    _tick(page, "#disc-dd-menu-1", value)


def _pick_discipline(page: Page, value) -> None:
    _open(page, "#disc-dd-btn-2", "#disc-dd-menu-2")
    _tick(page, "#disc-dd-menu-2", value)


@pytest.mark.django_db(transaction=True)
def test_create_with_multiple_disciplines_across_directions(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category, mtb_discipline
):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    page.fill("#id_title_ru", "Multi Disc Race")
    page.fill("#id_date_start", "2026-09-01")
    _pick_direction(page, road_category.pk)
    _pick_direction(page, mtb_category.pk)
    _pick_discipline(page, road_discipline.pk)
    _pick_discipline(page, mtb_discipline.pk)
    expect(page.locator("#disciplines-hidden input[name='disciplines']")).to_have_count(2)
    page.evaluate("() => document.getElementById('id_title_ru').form.requestSubmit()")
    page.wait_for_url(lambda url: "/calendar/submit/" not in url)

    comp = Competition.objects.get(title_ru="Multi Disc Race")
    assert set(comp.disciplines.values_list("pk", flat=True)) == {road_discipline.pk, mtb_discipline.pk}


@pytest.mark.django_db(transaction=True)
def test_edit_prefilled_then_add_another_discipline(
    page: Page, live_server, organizer, road_category, road_discipline, mtb_category, mtb_discipline
):
    comp = Competition.objects.create(
        title_ru="Editable Disc",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    comp.disciplines.set([road_discipline])
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/{comp.pk}/edit/")
    expect(page.locator(f"#disciplines-hidden input[value='{road_discipline.pk}']")).to_have_count(1)
    _pick_direction(page, mtb_category.pk)
    _pick_discipline(page, mtb_discipline.pk)
    expect(page.locator("#disciplines-hidden input[name='disciplines']")).to_have_count(2)
    page.evaluate("() => document.getElementById('id_title_ru').form.requestSubmit()")
    page.wait_for_url(lambda url: f"/calendar/{comp.pk}/edit/" not in url)

    comp.refresh_from_db()
    assert set(comp.disciplines.values_list("pk", flat=True)) == {road_discipline.pk, mtb_discipline.pk}


@pytest.mark.django_db(transaction=True)
def test_detail_shows_discipline_name_in_active_locale(page: Page, live_server, organizer):
    cat = DisciplineCategory.objects.create(name_ru="DirRU", name_en="DirEN", name_kk="DirKK", order=1)
    disc = Discipline.objects.create(name_ru="RoadRU", name_kk="RoadKK", name_en="RoadEN", category=cat, order=1)
    comp = Competition.objects.create(
        title_ru="LocaleRace",
        title_en="LocaleRace",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    comp.disciplines.set([disc])
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/{comp.pk}/")
    expect(page.locator("body")).to_contain_text("RoadRU")  # ru is the default UI locale
    switch_locale(page, "en")
    expect(page.locator("body")).to_contain_text("RoadEN")
    switch_locale(page, "kk")
    expect(page.locator("body")).to_contain_text("RoadKK")


@pytest.mark.django_db(transaction=True)
def test_picker_falls_back_for_incomplete_translation(page: Page, live_server, organizer):
    # Disciplines/category with no kk translation: the picker must show the fallback (ru) names as
    # DISTINCT options, not blank ones that the cascade would merge into a single checkbox.
    cat = DisciplineCategory.objects.create(name_ru="DirRU", name_en="DirEN", name_kk="", order=1)
    d1 = Discipline.objects.create(name_ru="OneRU", name_en="OneEN", name_kk="", category=cat, order=1)
    d2 = Discipline.objects.create(name_ru="TwoRU", name_en="TwoEN", name_kk="", category=cat, order=2)
    inject_session(page, live_server, organizer)
    host = live_server.url.split("//")[1].split(":")[0]
    page.context.add_cookies([{"name": "django_language", "value": "kk", "domain": host, "path": "/"}])
    page.goto(f"{live_server.url}/calendar/submit/")
    _pick_direction(page, cat.pk)
    _open(page, "#disc-dd-btn-2", "#disc-dd-menu-2")
    # Two distinct discipline checkboxes (the bug merged the two blank names into one).
    expect(page.locator("#disc-dd-menu-2 input.mf-item")).to_have_count(2)
    expect(page.locator(f"#disc-dd-menu-2 input.mf-item[value='{d1.pk}']")).to_have_count(1)
    expect(page.locator(f"#disc-dd-menu-2 input.mf-item[value='{d2.pk}']")).to_have_count(1)
