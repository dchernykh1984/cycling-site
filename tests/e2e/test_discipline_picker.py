"""E2E tests for the direction -> discipline picker on the competition submit/edit forms.

The picker reuses the searchable multi-select cascade from the event filters: pick one or
more directions, then tick the disciplines that get attached to the competition. These run a
real browser because the selection is wired entirely in JavaScript (hidden inputs are built
on the fly), which Django template-level tests cannot exercise.
"""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition, Discipline
from tests.e2e.conftest import inject_session


def _pick_direction(page: Page, value) -> None:
    page.click("#disc-dd-btn-1")
    page.click(f"#disc-dd-menu-1 input.mf-item[value='{value}']")


def _pick_discipline(page: Page, value) -> None:
    page.click("#disc-dd-btn-2")
    page.click(f"#disc-dd-menu-2 input.mf-item[value='{value}']")


@pytest.mark.django_db(transaction=True)
def test_orphan_discipline_is_selectable_without_direction(page: Page, live_server, organizer):
    # A discipline whose category was cleared in the admin must still be reachable, under the
    # synthetic "Without direction" group, and savable (review: category is nullable).
    orphan = Discipline.objects.create(name_ru="OrphanRU", name_en="Orphan", category=None, order=1)
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    page.fill("#id_title_ru", "Orphan Race")
    page.fill("#id_date_start", "2026-09-01")
    _pick_direction(page, "__none__")
    _pick_discipline(page, orphan.pk)
    expect(page.locator(f"#disciplines-hidden input[name='disciplines'][value='{orphan.pk}']")).to_have_count(1)
    page.evaluate("() => document.getElementById('id_title_ru').form.requestSubmit()")
    page.wait_for_url(lambda url: "/calendar/submit/" not in url)

    comp = Competition.objects.get(title_ru="Orphan Race")
    assert list(comp.disciplines.values_list("pk", flat=True)) == [orphan.pk]


@pytest.mark.django_db(transaction=True)
def test_edit_prefills_orphan_discipline(page: Page, live_server, organizer):
    orphan = Discipline.objects.create(name_ru="OrphanRU", name_en="Orphan", category=None, order=1)
    comp = Competition.objects.create(
        title_ru="Has Orphan",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    comp.disciplines.set([orphan])
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/{comp.pk}/edit/")
    # The previously-attached orphan is mirrored into a hidden input on load.
    expect(page.locator(f"#disciplines-hidden input[name='disciplines'][value='{orphan.pk}']")).to_have_count(1)
