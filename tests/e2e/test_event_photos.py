"""An athlete goes through their race album in a browser: confirms a photo, crosses another out,
undoes the cross, and crosses it out for good. The folder is a fake; nothing reaches Dropbox."""

import datetime
import tempfile

import pytest
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from event_photos import actions
from event_photos.models import ExternalAlbum, IssuedBib, PhotoDecision
from registrations.models import CompetitionRegistration
from tests.e2e.conftest import inject_session
from tests.test_event_photos import FOLDER, FakeAdapter, _index, _photo


@pytest.mark.django_db(transaction=True)
def test_an_athlete_marks_photos_and_undoes_a_cross(page: Page, live_server, settings):
    settings.EVENT_PHOTOS_ADAPTER = "tests.test_event_photos.FakeAdapter"
    settings.MEDIA_ROOT = tempfile.mkdtemp()
    athlete = User.objects.create_user(username="rider", email="rider@example.com", role=User.Role.PARTICIPANT)
    race = Competition.objects.create(
        title_ru="Alatau XCO", date_start=datetime.date.today(), status=Competition.Status.APPROVED
    )
    reg = CompetitionRegistration.objects.create(
        competition=race,
        user=athlete,
        first_name="Ivan",
        last_name="Rider",
        birth_date=datetime.date(1990, 1, 1),
        gender="M",
    )
    IssuedBib.objects.create(competition=race, registration=reg, bib="12")
    album = ExternalAlbum.objects.create(competition=race, folder_url=FOLDER, title="Folder A")
    FakeAdapter.files = {
        actions.INDEX_FILE: _index([_photo(1, [("12", "accepted", "ocr")]), _photo(2, [("12", "candidate", "ocr")])])
    }
    actions.import_album(album, None)

    with translation_override("ru"):
        mine, yes, no, undo = (gettext(s) for s in ("Photos with me", "This is me", "Not me", "Undo"))
    inject_session(page, live_server, athlete)
    with translation_override("ru"):
        counters = gettext("Confirmed: %(confirmed)s. To check: %(to_check)s.") % {"confirmed": 1, "to_check": 1}
    page.goto(f"{live_server.url}/ru/calendar/{race.pk}/photos/")
    expect(page.locator(".event-photo-cards")).to_contain_text(counters)
    page.goto(f"{live_server.url}/ru{race.get_absolute_url()[3:]}")
    page.get_by_role("link", name=mine).click()
    cards = page.locator(".event-photo")
    expect(cards).to_have_count(2)

    for button in page.locator(".event-photo-marks .btn").all():
        box = button.bounding_box()
        assert box is not None and box["height"] >= 44 and box["width"] >= 44, box

    candidate = cards.filter(has_text="IMG_0002.jpg")
    candidate.get_by_role("button", name=yes).click()
    expect(page.locator(".event-photo").filter(has_text="IMG_0002.jpg").get_by_role("button", name=yes)).to_have_count(
        0
    )

    page.locator(".event-photo").filter(has_text="IMG_0002.jpg").get_by_role("button", name=no).click()
    expect(page.locator(".event-photo")).to_have_count(1)
    page.get_by_role("button", name=undo).click()
    expect(page.locator(".event-photo")).to_have_count(2)

    page.locator(".event-photo").filter(has_text="IMG_0002.jpg").get_by_role("button", name=no).click()
    expect(page.locator(".event-photo")).to_have_count(1)
    expect(page.locator(".event-photo a").first).to_have_attribute("target", "_blank")

    # Own confirmations survive a later removal of the start-list bib.
    accepted = album.photos.get(original_path="IMG_0001.jpg")
    actions.decide(reg, accepted, PhotoDecision.State.ME, athlete)
    IssuedBib.objects.filter(registration=reg).delete()
    page.reload()
    expect(page.locator(".event-photo")).to_have_count(1)
    expect(page.locator(".event-photo")).to_contain_text("IMG_0001.jpg")
