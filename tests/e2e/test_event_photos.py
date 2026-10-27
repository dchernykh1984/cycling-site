"""An athlete goes through their race album in a browser: confirms a photo, crosses another out,
undoes the cross, and crosses it out for good. The folder is a fake; nothing reaches Dropbox."""

import datetime
import re
import tempfile
import time
import zipfile
from io import BytesIO

import pytest
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from PIL import Image
from playwright.sync_api import Page, expect

from accounts.models import User
from calendar_app.models import Competition
from event_photos import actions
from event_photos.models import ExternalAlbum, IssuedBib, PhotoDecision
from registrations.models import CompetitionRegistration
from tests.e2e.conftest import inject_session
from tests.test_event_photos import FOLDER, FakeAdapter, _index, _photo


@pytest.fixture
def indexed_event(settings, monkeypatch):
    settings.EVENT_PHOTOS_ADAPTER = "tests.test_event_photos.FakeAdapter"
    settings.MEDIA_ROOT = tempfile.mkdtemp()
    data = BytesIO()
    Image.new("RGB", (120, 240), "teal").save(data, "JPEG")
    monkeypatch.setattr(FakeAdapter, "thumbnail", lambda self, folder, path: data.getvalue())
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

    return athlete, race, reg, album


@pytest.mark.django_db(transaction=True)
def test_an_athlete_marks_photos_and_undoes_a_cross(page: Page, live_server, indexed_event):
    athlete, race, reg, album = indexed_event
    with translation_override("ru"):
        yes, no, undo, overview = (gettext(s) for s in ("This is me", "Not me", "Undo", "Photos from the event"))
    inject_session(page, live_server, athlete)
    with translation_override("ru"):
        counters = gettext("Confirmed: %(confirmed)s. To check: %(to_check)s.") % {"confirmed": 1, "to_check": 1}
    page.goto(f"{live_server.url}/ru/calendar/{race.pk}/photos/")
    expect(page.locator(".event-photo-cards")).to_contain_text(counters)
    page.goto(f"{live_server.url}/ru{race.get_absolute_url()[3:]}")
    page.get_by_role("link", name=overview, exact=True).click()
    page.locator(".event-photo-cards a").click()
    crumbs = page.get_by_role("navigation", name=gettext("Breadcrumb"))
    expect(crumbs.locator('[aria-current="page"]')).to_contain_text("Rider Ivan")
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


@pytest.mark.django_db(transaction=True)
def test_retrying_a_rejection_keeps_the_original_undo(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    inject_session(page, live_server, athlete)
    page.goto(f"{live_server.url}/ru/calendar/{race.pk}/photos/registration/{reg.pk}/")
    form = page.locator(".event-photo").filter(has_text="IMG_0002.jpg").locator('form:has(input[value="not_me"])')
    data: dict[str, str | float | bool] = {
        "state": "not_me",
        "csrfmiddlewaretoken": form.locator('input[name="csrfmiddlewaretoken"]').input_value(),
    }
    url = live_server.url + form.get_attribute("action")
    first = page.request.post(url, form=data, max_redirects=0)
    repeated = page.request.post(url, form=data, max_redirects=0)
    assert first.status == repeated.status == 302
    assert first.headers["location"] == repeated.headers["location"]
    page.goto(live_server.url + repeated.headers["location"])
    with translation_override("ru"):
        undo = gettext("Undo")
    page.get_by_role("button", name=undo).click()
    expect(page.locator(".event-photo")).to_have_count(2)


@pytest.mark.django_db(transaction=True)
def test_portraits_are_complete_and_captions_never_cover_them(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    inject_session(page, live_server, athlete)
    for width in (360, 768, 1024, 320):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(f"{live_server.url}/kk/calendar/{race.pk}/photos/registration/{reg.pk}/")
        image = page.locator(".event-photo img").first
        expect(image).to_be_visible()
        assert image.evaluate("el => el.naturalHeight > el.naturalWidth")
        assert image.evaluate("el => getComputedStyle(el).objectFit") == "contain"
        assert image.get_attribute("alt") == ""  # the adjacent filename already names the link
        frame = image.locator("..").bounding_box()
        caption = page.locator(".event-photo .gallery-card-caption").first.bounding_box()
        assert frame and caption and caption["y"] >= frame["y"] + frame["height"] - 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator(".event-photo a").first.hover()
    assert image.evaluate("el => getComputedStyle(el).transform") in ("none", "matrix(1, 0, 0, 1, 0, 0)")


@pytest.mark.django_db(transaction=True)
def test_curated_albums_use_the_same_photo_entry(page: Page, live_server, indexed_event):
    from gallery.models import Album

    _, race, _, _ = indexed_event
    album = Album.objects.create(title_ru="Curated photos", date=race.date_start, competition=race)
    page.goto(f"{live_server.url}/en/calendar/{race.pk}/")
    expect(page.locator(".competition-albums")).to_have_count(0)
    page.get_by_role("link", name="Photos from the event", exact=True).click()
    with translation_override("en"):
        expected_url = album.get_absolute_url()
    expect(page.get_by_role("link", name=album.title)).to_have_attribute("href", expected_url)


@pytest.mark.django_db(transaction=True)
def test_missing_preview_reserves_the_same_frame_as_a_loaded_photo(page: Page, live_server, indexed_event):
    athlete, race, reg, album = indexed_event
    photo = album.photos.get(original_path="IMG_0001.jpg")
    photo.original_bytes = 21 * 1024 * 1024
    photo.save(update_fields=["original_bytes"])
    inject_session(page, live_server, athlete)
    page.goto(f"{live_server.url}/en/calendar/{race.pk}/photos/registration/{reg.pk}/")
    blank = page.locator(".event-photo .gallery-card-blank").bounding_box()
    assert blank and abs(blank["width"] / blank["height"] - 1.5) < 0.01


@pytest.mark.django_db(transaction=True)
def test_unavailable_previews_keep_the_original_link_and_have_no_broken_image(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    inject_session(page, live_server, athlete)
    page.route("**/photos/thumb/**", lambda route: route.fulfill(status=404))
    page.goto(f"{live_server.url}/en/calendar/{race.pk}/photos/registration/{reg.pk}/")
    expect(page.locator("[data-photo-unavailable]").first).to_be_visible()
    expect(page.locator(".event-photo img").first).to_be_hidden()
    expect(page.locator(".event-photo a").first).to_have_attribute("href", re.compile("preview=IMG_0001.jpg"))


@pytest.mark.django_db(transaction=True)
def test_a_busy_server_delays_previews_without_losing_them(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    busy: dict[str, int] = {}

    def answer(route):
        # Three busy replies per preview: more than the old two retries allowed.
        url = route.request.url
        busy[url] = busy.get(url, 0) + 1
        if busy[url] <= 3:
            route.fulfill(status=503, headers={"Retry-After": "1"})
        else:
            route.continue_()

    page.route("**/photos/thumb/**", answer)
    inject_session(page, live_server, athlete)
    page.goto(f"{live_server.url}/en/calendar/{race.pk}/photos/registration/{reg.pk}/")
    expect(page.locator(".event-photo img").first).to_be_visible(timeout=20000)
    expect(page.locator("[data-photo-unavailable]").first).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_a_preview_is_not_asked_again_before_the_server_allows(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    asked: dict[str, list[float]] = {}

    def answer(route):
        times = asked.setdefault(route.request.url, [])
        times.append(time.monotonic())
        if len(times) == 1:
            route.fulfill(status=503, headers={"Retry-After": "3"})
        else:
            route.continue_()

    page.route("**/photos/thumb/**", answer)
    page.add_init_script("Math.random = function () { return 0; };")  # the shortest spread the page can pick
    inject_session(page, live_server, athlete)
    page.goto(f"{live_server.url}/en/calendar/{race.pk}/photos/registration/{reg.pk}/")
    expect(page.locator(".event-photo img").first).to_be_visible(timeout=20000)
    for first, second in (times[:2] for times in asked.values() if len(times) > 1):
        assert second - first >= 2.9


@pytest.mark.django_db(transaction=True)
def test_slow_previews_do_not_block_marks_or_start_a_request_storm(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    FakeAdapter.files[actions.INDEX_FILE] = _index(
        [_photo(n, [("12", "candidate", "ocr")]) for n in range(1, 21)], revision=2
    )
    actions.import_album(race.external_albums.get(), None)
    # Downloads are never answered. One the page gives up on -- after 10 s, or on leaving for the
    # redirected page -- frees its place for the next, so what is counted is how many are open at once.
    open_now, at_once = set(), []

    def hold(route):
        open_now.add(route.request)
        at_once.append(len(open_now))

    page.route("**/photos/thumb/**", hold)
    page.on("requestfailed", lambda request: open_now.discard(request))
    inject_session(page, live_server, athlete)
    page.goto(f"{live_server.url}/en/calendar/{race.pk}/photos/registration/{reg.pk}/")
    expect(page.locator(".event-photo")).to_have_count(20)
    page.wait_for_function("document.querySelectorAll('img[data-photo-src]').length === 20")
    # Two downloads stay blocked; marking still completes instead of waiting for those downloads.
    page.locator(".event-photo").first.get_by_role("button", name="This is me").click()
    expect(page.locator(".event-photo").first.get_by_role("button", name="This is me")).to_have_count(0)
    assert at_once and max(at_once) <= 2, at_once


@pytest.mark.django_db(transaction=True)
def test_undo_restores_the_last_photo_to_its_original_gallery_page(page: Page, live_server, indexed_event, monkeypatch):
    from django.urls import reverse

    from event_photos import views

    athlete, race, reg, _ = indexed_event
    monkeypatch.setattr(views, "PER_PAGE", 1)
    with translation_override("ru"):
        no, undo = gettext("Not me"), gettext("Undo")
        path = reverse("event_photos:registration", args=[race.pk, reg.pk])
    inject_session(page, live_server, athlete)
    page.goto(f"{live_server.url}{path}?page=2")
    expect(page.locator(".event-photo")).to_have_count(1)
    expect(page.locator(".event-photo")).to_contain_text("IMG_0002.jpg")
    page.get_by_role("button", name=no).click()
    undo_button = page.get_by_role("button", name=undo)
    form = page.locator("form").filter(has=undo_button)
    expect(form.locator('input[name="page"]')).to_have_value("2")
    undo_button.click()
    expect(page).to_have_url(re.compile(r"[?]page=2$"))
    expect(page.locator(".event-photo")).to_contain_text("IMG_0002.jpg")


@pytest.mark.django_db(transaction=True)
def test_download_all_gives_the_album_as_one_zip_from_a_phone_sized_button(page: Page, live_server, indexed_event):
    athlete, race, reg, _ = indexed_event
    FakeAdapter.files.update({"IMG_0001.jpg": b"first original", "IMG_0002.jpg": b"second original"})
    with translation_override("ru"):
        label = gettext("Download all (ZIP, %(size)s)").split(" (")[0]
    inject_session(page, live_server, athlete)
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto(f"{live_server.url}/ru/calendar/{race.pk}/photos/registration/{reg.pk}/")
    button = page.get_by_role("link", name=re.compile(re.escape(label)))
    box = button.bounding_box()
    assert box is not None and box["height"] >= 44, box
    with page.expect_download() as caught:
        button.click()
    download = caught.value
    assert download.suggested_filename.endswith(".zip"), download.suggested_filename
    with zipfile.ZipFile(download.path()) as archive:
        assert sorted(archive.namelist()) == ["IMG_0001.jpg", "IMG_0002.jpg"]
        assert archive.read("IMG_0001.jpg") == b"first original"
