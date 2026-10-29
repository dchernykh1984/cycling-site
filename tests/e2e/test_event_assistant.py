"""E2E for the event assistant (issue #353): the event form's hooks, and the chat on the add and edit pages."""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from assistant import llm
from assistant.models import Conversation, Message
from calendar_app.models import Competition, Discipline, DisciplineCategory, EventType
from locations.models import Location
from tests.e2e.conftest import inject_session


def _tree():
    country = Location.add_root(name_ru="Testland", name_kk="Testland", name_en="Testland")
    region = country.add_child(name_ru="Test Region", name_kk="Test Region", name_en="Test Region")
    city = region.add_child(name_ru="Testville", name_kk="Testville", name_en="Testville", lat=43.24, lng=76.89)
    city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
    shop = city.add_child(name_ru="Giant shop", name_kk="Giant shop", name_en="Giant shop", lat=43.2389, lng=76.9453)
    return city, shop


@pytest.mark.django_db(transaction=True)
def test_the_place_cascade_takes_a_venue_or_a_new_one_from_a_script(page: Page, live_server, admin_user):
    city, shop = _tree()
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.evaluate(f"window.eventLocation.select({shop.pk})")
    expect(page.locator("#loc-city")).to_have_value(str(city.pk))
    expect(page.locator("#id_location")).to_have_value(str(shop.pk))
    page.evaluate(f"window.eventLocation.propose({city.pk}, {{ru: 'Most', kk: '', en: 'Bridge'}}, 43.25, 76.95)")
    expect(page.locator("#new-venue-box")).to_be_visible()
    expect(page.locator("#new-venue-name")).to_have_value("Most")
    expect(page.locator("#new-venue-name-en")).to_have_value("Bridge")
    expect(page.locator("#new-venue-lat")).to_have_value("43.250000")
    expect(page.locator("#id_location")).to_have_value("")
    expect(page.locator("#id_new_venue_city")).to_have_value(str(city.pk))


@pytest.mark.django_db(transaction=True)
def test_the_discipline_picker_takes_its_choice_from_a_script(page: Page, live_server, admin_user):
    road = DisciplineCategory.objects.create(name_ru="Shosse", name_en="Road Test")
    gravel = Discipline.objects.create(name_ru="Grevel", name_en="Gravel Test", category=road)
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.evaluate(f"window.eventDisciplines.set([{gravel.pk}])")
    chosen = page.locator("#disciplines-hidden input[name='disciplines']")
    expect(chosen).to_have_count(1)
    expect(chosen).to_have_value(str(gravel.pk))
    expect(page.locator("#disc-dd-btn-2 .mf-text")).to_have_text("Gravel Test")
    page.evaluate("window.eventDisciplines.set([])")
    expect(chosen).to_have_count(0)


GPX = '<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="43.25" lon="76.95"/></trkseg></trk></gpx>'


def _model(monkeypatch, *answers):
    """Stands in for the model, answering in turn; returns the prompts it was given."""
    asked: list = []

    def complete(messages):
        asked.append(messages)
        answer = answers[min(len(asked), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr("assistant.llm.complete", complete)
    return asked


def _box(locator):
    box = locator.bounding_box()
    assert box is not None
    return box


@pytest.fixture
def chat_on(settings):
    settings.ASSISTANT_LLM_API_KEY = "sk-test"


@pytest.mark.django_db(transaction=True)
def test_the_chat_fills_the_form_and_saving_links_it(page: Page, live_server, admin_user, chat_on, monkeypatch):
    _city, shop = _tree()
    ride = EventType.objects.create(name_ru="Zaezd", name_en="Ride test")
    gravel = Discipline.objects.create(
        name_ru="Grevel",
        name_en="Gravel test",
        category=DisciplineCategory.objects.create(name_ru="Shosse", name_en="Road test"),
    )
    answer = {
        "reply": "Filled it in.",
        "set": {
            "title": {"ru": "Kofe-raid", "kk": "Kofe-raid", "en": "Coffee ride"},
            "description": {"ru": "<p>Start 08:00</p>", "kk": "<p>Start 08:00</p>", "en": "<p>Start at 08:00</p>"},
            "date_start": "2026-10-31",
            "event_type_ids": [ride.pk],
            "discipline_ids": [gravel.pk],
            "url_route": "https://strava.com/routes/1",
            "place": {"city": "Testville", "venue": {"en": "Giant shop"}},
        },
    }
    _model(monkeypatch, answer)
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.click("#assistant-toggle")
    log = page.locator("#assistant-log")
    expect(log).to_contain_text("What event would you like to add?")
    page.fill("#assistant-text", "Coffee ride on Saturday, track https://strava.com/routes/1")
    page.click("#assistant-send")
    expect(log).to_contain_text("Filled it in.")
    expect(page.locator("#id_title_en")).to_have_value("Coffee ride")
    expect(page.locator("#id_date_start")).to_have_value("2026-10-31")
    expect(page.locator("#id_url_route")).to_have_value("https://strava.com/routes/1")
    expect(page.locator("#id_location")).to_have_value(str(shop.pk))
    expect(page.locator("#disciplines-hidden input[name='disciplines']")).to_have_value(str(gravel.pk))
    expect(page.locator("#quill-desc-en .ql-editor")).to_contain_text("Start at 08:00")
    assert page.eval_on_selector("#id_event_types", "s => Array.from(s.selectedOptions).map(o => o.value)") == [
        str(ride.pk)
    ]
    expect(page.locator("#assistant-text")).to_have_value("")
    page.locator("form button[type='submit']", has_text="Submit").click()
    page.wait_for_url(re.compile(r"/calendar/list/"))
    event = Competition.objects.get(title_en="Coffee ride")
    assert event.description_en == "<p>Start at 08:00</p>"
    assert [m.text for m in event.assistant_conversation.messages.all()] == [
        "Coffee ride on Saturday, track https://strava.com/routes/1",
        "Filled it in.",
    ]


@pytest.mark.django_db(transaction=True)
def test_on_a_phone_the_chat_takes_the_lower_screen_and_hides(page: Page, live_server, admin_user, chat_on):
    inject_session(page, live_server, admin_user)
    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/kk/calendar/submit/")
    toggle = page.locator("#assistant-toggle")
    box = _box(toggle)
    assert box["height"] >= 44 and box["x"] + box["width"] <= 360
    corner = _box(page.locator(".w-userbar-trigger"))
    assert box["x"] + box["width"] <= corner["x"], "the chat's button keeps clear of Wagtail's"
    toggle.click()
    panel = _box(page.locator("#assistant-panel"))
    assert (panel["x"], panel["width"]) == (0, 360)
    assert abs(panel["y"] + panel["height"] - 740) < 1 and panel["height"] < 740 * 0.65
    for control in ("#assistant-hide", "#assistant-attach", "#assistant-send"):
        assert _box(page.locator(control))["height"] >= 44, control
    expect(page.locator(".w-userbar-trigger")).to_be_hidden()
    page.click("#assistant-hide")
    expect(page.locator("#assistant-panel")).to_be_hidden()
    expect(toggle).to_be_visible()
    expect(page.locator(".w-userbar-trigger")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_the_edit_page_shows_the_conversation_and_goes_on_with_it(
    page: Page, live_server, admin_user, chat_on, monkeypatch
):
    _city, shop = _tree()
    event = Competition.objects.create(
        title_ru="Ride",
        date_start=datetime.date(2026, 10, 31),
        location=shop,
        submitted_by=admin_user,
        status=Competition.Status.APPROVED,
    )
    conversation = Conversation.objects.create(competition=event)
    Message.objects.create(conversation=conversation, role=Message.Role.USER, text="A ride on Saturday")
    Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT, text="Filled it in.")
    asked = _model(monkeypatch, {"reply": "Moved to Sunday.", "set": {"date_start": "2026-11-01"}})
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/{event.pk}/edit/")
    page.click("#assistant-toggle")
    log = page.locator("#assistant-log")
    said = log.locator(".assistant-msg")
    expect(said.first).to_have_text("A ride on Saturday")
    expect(said.last).to_have_text("What would you like to change in this event?")
    page.fill("#assistant-text", "Move it to Sunday")
    page.click("#assistant-send")
    expect(log).to_contain_text("Moved to Sunday.")
    expect(page.locator("#id_date_start")).to_have_value("2026-11-01")
    assert "editing an event already on the site" in asked[0][-1]["content"]
    assert asked[0][1]["content"] == "A ride on Saturday"


@pytest.mark.django_db(transaction=True)
def test_an_attached_track_goes_into_the_form_and_places_a_new_venue(
    page: Page, live_server, admin_user, chat_on, monkeypatch, tmp_path
):
    _tree()
    track = tmp_path / "ride.gpx"
    track.write_text(GPX)
    place = {"city": "Testville", "venue": {"ru": "Most", "en": "Bridge"}}
    _model(
        monkeypatch,
        {"reply": "Got the track. Where do you meet?", "set": {}},
        {"reply": "Noted.", "set": {"place": place}},
    )
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.click("#assistant-toggle")
    page.set_input_files("#assistant-file", str(track))
    log = page.locator("#assistant-log")
    expect(log).to_contain_text("Attached to the form as the route: ride.gpx")
    expect(log).to_contain_text("Got the track.")
    assert page.eval_on_selector("#id_file_route", "i => i.files.length ? i.files[0].name : ''") == "ride.gpx"
    page.fill("#assistant-text", "We meet at the bridge")
    page.click("#assistant-send")
    expect(page.locator("#new-venue-name")).to_have_value("Most")
    expect(page.locator("#new-venue-lat")).to_have_value("43.250000")
    expect(page.locator("#new-venue-lng")).to_have_value("76.950000")


@pytest.mark.django_db(transaction=True)
def test_when_the_model_cannot_answer_the_message_waits_to_be_sent_again(
    page: Page, live_server, admin_user, chat_on, monkeypatch
):
    _model(monkeypatch, llm.UnavailableError(llm.UnavailableError.BUSY))
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    page.click("#assistant-toggle")
    page.fill("#assistant-text", "A ride on Saturday")
    page.click("#assistant-send")
    log = page.locator("#assistant-log")
    expect(log.locator(".assistant-error")).to_contain_text("The model did not answer.")
    expect(log.locator(".assistant-from-user")).to_have_count(0)
    expect(page.locator("#assistant-text")).to_have_value("A ride on Saturday")
    assert not Message.objects.exists()
