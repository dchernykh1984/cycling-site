"""A date of birth typed as DD.MM.YYYY with the calendar on a button beside it (cycling_site/typed_date.py): the
dots come as the digits are typed, the calendar opens on the date typed and writes the date picked back, a date
the page cannot read is named before the form goes, and the field and its button fit a phone."""

import datetime

import pytest
from django.utils import translation
from playwright.sync_api import Page, expect

from accounts import virtual_members
from accounts.models import User, VirtualMember
from cycling_site.typed_date import FORMAT_ERROR
from tests.e2e.conftest import inject_session

#: Records the date each calendar was opened on, in place of the browser's own calendar a test cannot see.
PICKER_SPY = """HTMLInputElement.prototype.showPicker = function () {
  window.openedOn = (window.openedOn || []).concat(this.value);
};"""


@pytest.fixture
def member(db):
    return User.objects.create_user(
        username="typist", email="typist@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )


def _box(page: Page, selector: str) -> dict:
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return dict(box)


def _edit(page: Page, live_server, member, lang: str = "en"):
    page.add_init_script(PICKER_SPY)
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/{lang}/accounts/profile/edit/")


@pytest.mark.django_db(transaction=True)
def test_digits_typed_get_their_dots_and_the_date_is_saved(page: Page, live_server, member):
    _edit(page, live_server, member)
    field = page.locator("#id_birth_date")
    field.press_sequentially("05032012")
    expect(field).to_have_value("05.03.2012")
    # a day or a month typed with one digit and its own dot keeps it, and is written out in full when left
    field.fill("")
    field.press_sequentially("5.3.2012")
    field.press("Tab")
    expect(field).to_have_value("05.03.2012")
    page.locator("main form").get_by_role("button", name="Save").click()
    expect(page).to_have_url(f"{live_server.url}/en/accounts/profile/")
    member.refresh_from_db()
    assert member.birth_date == datetime.date(2012, 3, 5)


@pytest.mark.django_db(transaction=True)
def test_the_calendar_opens_on_the_date_typed_and_writes_the_date_picked_back(page: Page, live_server, member):
    _edit(page, live_server, member)
    field = page.locator("#id_birth_date")
    field.fill("21.06.1990")
    # a tap or a click lands on the date input over the button; the keyboard reaches the button itself
    page.locator(".typed-date-pick").click()
    page.get_by_role("button", name="Calendar").press("Enter")
    assert page.evaluate("window.openedOn") == ["1990-06-21", "1990-06-21"]
    page.locator(".typed-date-pick input[type=date]").evaluate(
        "el => { el.value = '1985-03-10'; el.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    expect(field).to_have_value("10.03.1985")
    # an empty field opens the calendar on today, as the browser does
    field.fill("")
    page.locator(".typed-date-pick").click()
    assert page.evaluate("window.openedOn.at(-1)") == ""


@pytest.mark.django_db(transaction=True)
def test_a_date_that_cannot_be_read_is_named_and_the_form_waits_for_it(page: Page, live_server, member):
    _edit(page, live_server, member)
    field, error = page.locator("#id_birth_date"), page.locator(".typed-date-error")
    field.fill("31.02.2012")
    field.press("Tab")
    with translation.override("en"):
        expect(error).to_have_text(str(FORMAT_ERROR))
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(field).to_have_attribute("aria-describedby", "id_birth_date_typed_error")
    page.locator("main form").get_by_role("button", name="Save").click()
    expect(field).to_be_focused()
    expect(page).to_have_url(f"{live_server.url}/en/accounts/profile/edit/")
    # put right, the reason goes as soon as the date can be read
    field.fill("28.02.2012")
    expect(error).to_be_hidden()
    expect(field).not_to_have_attribute("aria-invalid", "true")
    # a date of birth after today is named too, before the server is asked
    field.fill("01.01.2999")
    field.press("Tab")
    expect(error).to_have_text("Enter a date of birth between 1900 and today.")


@pytest.mark.django_db(transaction=True)
def test_on_a_phone_the_field_and_its_button_fit_and_are_big_enough_to_tap(page: Page, live_server, member):
    page.set_viewport_size({"width": 360, "height": 740})
    _edit(page, live_server, member, "kk")  # the longest of the three words for the button
    box, field, button, calendar = (
        _box(page, selector)
        for selector in (".typed-date", "#id_birth_date", ".typed-date-pick .btn", ".typed-date-pick input[type=date]")
    )
    assert field["height"] >= 44 and button["height"] >= 44 and button["width"] >= 44, (field, button)
    assert button["x"] + button["width"] <= box["x"] + box["width"] + 0.5, (button, box)
    assert field["width"] >= 110, field  # room for 00.00.0000
    # the date input lies over the whole button, so a tap anywhere on it opens the calendar
    assert all(abs(calendar[k] - button[k]) < 1 for k in ("x", "y", "width", "height")), (calendar, button)
    assert page.evaluate("document.documentElement.scrollWidth") <= 360


@pytest.mark.django_db(transaction=True)
def test_the_card_s_span_of_dates_of_birth_is_typed_as_well(page: Page, live_server, member):
    virtual_members.consent(member)
    for last, born in (
        ("Sokolova", datetime.date(2012, 3, 4)),
        ("Kim", datetime.date(2013, 1, 9)),
        ("Pak", datetime.date(2012, 7, 7)),
    ):
        VirtualMember.objects.create(owner=member, last_name=last, first_name="A", gender="F", birth_date=born)
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    card = page.locator("#virtual-members")
    shown = card.locator(".virtual-people > li:visible")
    expect(shown).to_have_count(3)
    card.locator("#vm-born-from").press_sequentially("01012012")
    card.locator("#vm-born-to").press_sequentially("31122012")
    expect(card.locator("#vm-born-to")).to_have_value("31.12.2012")
    expect(shown).to_have_count(2)
    expect(card.locator(".vm-shown")).to_have_text("2")
