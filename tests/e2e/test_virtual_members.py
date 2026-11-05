"""E2E for the people without accounts a member adds (issue #438) and the registration page that enters
them (issues #439, #440): the profile's card -- the member's word first, then the people, their
filters and a fold kept for the browser -- and the page's filters by name, team and category."""

import datetime

import pytest
from playwright.sync_api import Page, expect

from accounts import virtual_members
from accounts.models import User, VirtualMember
from calendar_app.models import Competition
from registrations.models import CompetitionRegistration, RegistrationCategory
from tests.e2e.conftest import UPCOMING, inject_session
from tests.e2e.contrast import is_large, legibility
from tests.e2e.test_skin_contrast import KNOWN_SHORTFALLS, NO_FADES, _in_state

#: "Sokolova" in Cyrillic: the filters find a name typed in either script.
SOKOLOVA_CYRILLIC = "\u0421\u043e\u043a\u043e\u043b\u043e\u0432\u0430"


@pytest.fixture
def coach(db):
    return User.objects.create_user(
        username="coach",
        email="coach@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        first_name="Ivan",
        last_name="Petrov",
        gender="M",
        birth_date=datetime.date(1985, 5, 5),
    )


def _sign_in(page, live_server, user):
    page.context.clear_cookies()
    inject_session(page, live_server, user)


def _add(owner, last_name, first_name, gender, born, team=""):
    return VirtualMember.objects.create(
        owner=owner, last_name=last_name, first_name=first_name, gender=gender, birth_date=born, team=team
    )


def _section(owner):
    """Six children in two teams and one with none: more than the page shows without filters."""
    virtual_members.consent(owner)
    return {
        "sokolova": _add(owner, "Sokolova", "Dana", "F", datetime.date(2012, 3, 4), "Snow Leopards"),
        "bekova": _add(owner, "Bekova", "Aru", "F", datetime.date(2011, 6, 1), "Snow Leopards"),
        "li": _add(owner, "Li", "Mira", "F", datetime.date(2009, 9, 9)),
        "kim": _add(owner, "Kim", "Oleg", "M", datetime.date(2013, 1, 9), "Eagles"),
        "ten": _add(owner, "Ten", "Arman", "M", datetime.date(2010, 2, 2), "Eagles"),
        "pak": _add(owner, "Pak", "Timur", "M", datetime.date(2012, 7, 7), "Eagles"),
    }


def _event(organizer):
    comp = Competition.objects.create(
        title_ru="Section Race",
        date_start=UPCOMING,
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        registration_enabled=True,
        registration_mode=Competition.RegistrationMode.SELF_ONLY,
        birth_date_mode=Competition.BirthDateMode.YEAR,
    )
    young = {"birth_from": datetime.date(2008, 1, 1), "birth_to": datetime.date(2014, 12, 31)}
    RegistrationCategory.objects.create(competition=comp, name="Girls", male=False, female=True, **young)
    RegistrationCategory.objects.create(competition=comp, name="Boys", male=True, female=False, **young)
    RegistrationCategory.objects.create(competition=comp, name="Adults", male=True, female=True)
    return comp


@pytest.mark.django_db(transaction=True)
def test_the_card_takes_the_members_word_first_and_then_adds_a_person(page: Page, live_server, coach):
    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    card = page.locator("#virtual-members")
    expect(card.locator(".virtual-add")).to_have_count(0)
    card.get_by_role("button", name="I am authorized to handle their personal data").click()
    card = page.locator("#virtual-members")
    card.locator("#id_last_name").fill("Sokolova")
    card.locator("#id_first_name").fill("Dana")
    card.locator("#id_gender").select_option("F")
    card.locator("#id_birth_date").fill("2012-03-04")
    card.get_by_role("button", name="Add", exact=True).click()
    expect(page.locator("#virtual-members .virtual-people")).to_contain_text("Sokolova Dana")
    expect(page.locator("#virtual-members")).to_contain_text("Added: 1 of 10")
    assert VirtualMember.objects.filter(owner=coach, last_name="Sokolova", first_name="Dana").exists()


@pytest.mark.django_db(transaction=True)
def test_the_cards_filters_find_a_name_in_either_script_a_team_and_a_span_of_birth_dates(
    page: Page, live_server, coach
):
    _section(coach)
    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    card = page.locator("#virtual-members")
    shown = card.locator(".virtual-people > li:visible")
    card.locator("#vm-name").fill(SOKOLOVA_CYRILLIC)
    expect(shown).to_have_count(1)
    expect(shown).to_contain_text("Sokolova Dana")
    card.locator("#vm-name").fill("")
    card.locator("#vm-team").select_option("Eagles")
    expect(shown).to_have_count(3)
    card.locator("#vm-born-from").fill("2012-01-01")
    card.locator("#vm-born-to").fill("2012-12-31")
    expect(shown).to_have_count(1)
    expect(shown).to_contain_text("Pak Timur")
    expect(card.locator(".vm-shown")).to_have_text("1")


@pytest.mark.django_db(transaction=True)
def test_the_card_folded_once_stays_folded_in_this_browser(page: Page, live_server, coach):
    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    card = page.locator("#virtual-members")
    expect(card).to_have_attribute("open", "")
    card.locator("summary").click()
    page.reload()
    expect(page.locator("#virtual-members")).not_to_have_attribute("open", "")
    expect(page.locator("#virtual-members .card-body")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_the_registration_filters_narrow_the_list_and_a_hidden_tick_is_still_sent(
    page: Page, live_server, organizer, coach
):
    people = _section(coach)
    comp = _event(organizer)
    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/competitions/{comp.pk}/register/")
    for key in ("sokolova", "kim"):
        page.locator(f"#person-v{people[key].pk} .register-person-check").check()
    shown = page.locator(".register-person[data-name]:visible")
    summary = page.locator("#rf-summary")
    expect(summary).to_have_text("Ticked: 2")

    page.locator("#rf-name").fill(SOKOLOVA_CYRILLIC)
    expect(shown).to_have_count(1)
    expect(shown).to_contain_text("Sokolova Dana")
    expect(summary).to_have_text("Ticked: 2, of them hidden by the filters: 1")

    page.locator("#rf-name").fill("")
    page.locator("#rf-team").select_option("Eagles")
    expect(shown).to_have_count(3)
    page.locator("#rf-team").select_option("")

    page.locator("#rf-categories").click()
    page.locator("#rf-categories-menu label", has_text="Girls").click()
    expect(page.locator("#rf-categories .mf-text")).to_have_text("Girls")
    expect(shown).to_have_count(3)
    expect(page.locator(f"#person-v{people['kim'].pk}")).to_be_hidden()

    page.locator("#registration-form > button[type='submit']").click()
    expect(page).to_have_url(f"{live_server.url}/en/competitions/{comp.pk}/participants/")
    entered = CompetitionRegistration.objects.filter(competition=comp)
    assert set(entered.values_list("virtual_member", "category__name")) == {
        (people["sokolova"].pk, "Girls"),
        (people["kim"].pk, "Boys"),
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_on_a_phone_the_card_and_the_filters_take_a_tap_and_nothing_scrolls_sideways(
    page: Page, live_server, organizer, coach, lang
):
    _section(coach)
    comp = _event(organizer)
    page.set_viewport_size({"width": 360, "height": 800})
    _sign_in(page, live_server, coach)
    small = []
    for path, controls in (
        (
            "/accounts/profile/",
            "#virtual-members > summary, .virtual-members .btn, .virtual-filters .form-control, "
            ".virtual-filters .form-select",
        ),
        (
            f"/competitions/{comp.pk}/register/",
            ".register-filters .form-control, .register-filters .form-select, .register-filters .btn, "
            ".register-person-toggle",
        ),
    ):
        page.goto(f"{live_server.url}/{lang}{path}")
        assert page.evaluate("document.scrollingElement.scrollWidth <= document.scrollingElement.clientWidth")
        for control in page.locator(controls).all():
            box = control.bounding_box()
            # to a tenth of a pixel: Firefox lays a 44 px line out as 43.99997
            if box and round(box["height"], 1) < 44:
                small.append((path, control.inner_text(), box["height"]))
    assert not small, small


# Whether a select shows its chosen option whole: the text in the select's own font against the room
# between its paddings, the right one holding the arrow.
SHOWS_ITS_CHOICE_WHOLE = """(el) => {
  const style = getComputedStyle(el), probe = document.createElement('span');
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap';
  probe.style.font = style.font;
  probe.textContent = el.options[el.selectedIndex].text;
  document.body.appendChild(probe);
  const needs = probe.getBoundingClientRect().width + parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  probe.remove();
  return needs <= el.clientWidth + 0.5;
}"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [360, 1280])
def test_the_filters_and_the_form_show_their_choices_whole_in_the_longest_language(
    page: Page, live_server, organizer, coach, width
):
    """Kazakh's words are the longest: a team or a gender cut to a few letters, or a category's name
    spilling past its button, is what three columns in a narrow card did."""
    _section(coach)
    comp = _event(organizer)
    page.set_viewport_size({"width": width, "height": 900})
    _sign_in(page, live_server, coach)
    cut = []
    for path, selects in (
        ("/kk/accounts/profile/", "#vm-team, #id_gender"),
        (f"/kk/competitions/{comp.pk}/register/", "#rf-team"),
    ):
        page.goto(f"{live_server.url}{path}")
        for select in page.locator(selects).all():
            if not select.evaluate(SHOWS_ITS_CHOICE_WHOLE):
                cut.append((path, select.get_attribute("id")))
    page.locator("#rf-categories").click()
    page.locator("#rf-categories-menu label", has_text="Girls").click()
    named = page.locator("#rf-categories .mf-text")
    expect(named).to_have_text("Girls")
    assert named.evaluate("el => el.scrollWidth <= el.clientWidth")
    assert not cut, cut


@pytest.mark.django_db(transaction=True)
def test_what_the_card_and_the_page_add_reads_in_this_skin(page: Page, live_server, organizer, coach):
    """Text at least 4.5:1 (3:1 large) in the skin the suite runs in, as test_skin_contrast asks of the
    shared pages; muted text keeps the allowance that file records for light."""
    from django.conf import settings

    people = _section(coach)
    comp = _event(organizer)
    _sign_in(page, live_server, coach)
    toggle = f"#person-v{people['sokolova'].pk} .register-person-toggle"
    checks = (
        ("/en/accounts/profile/", "card header", "#virtual-members > summary", ("rest",)),
        ("/en/accounts/profile/", "count", "#virtual-members > summary .badge", ("rest",)),
        ("/en/accounts/profile/", "muted text", ".virtual-people .text-muted", ("rest",)),
        # Delete is the site's outline-danger, as everywhere a member removes something: its red is the
        # skin's, short of 4.5:1 in light and orange alike, and stays theirs to change.
        ("/en/accounts/profile/", "edit", ".virtual-people .btn-outline-primary", ("rest", "hover", "focus")),
        (f"/en/competitions/{comp.pk}/register/", "label", ".register-filters label", ("rest",)),
        (f"/en/competitions/{comp.pk}/register/", "categories", "#rf-categories", ("rest", "focus")),
        (f"/en/competitions/{comp.pk}/register/", "muted text", "#rf-summary", ("rest",)),
        (f"/en/competitions/{comp.pk}/register/", "no account", ".register-person-pick .badge", ("rest",)),
        (f"/en/competitions/{comp.pk}/register/", "category", ".register-person-category", ("rest",)),
        (f"/en/competitions/{comp.pk}/register/", "details", toggle, ("rest", "hover", "focus")),
    )
    shortfalls = []
    for path in dict.fromkeys(check[0] for check in checks):
        page.goto(f"{live_server.url}{path}")
        page.add_style_tag(content=NO_FADES)
        for check_path, what, selector, states in checks:
            if check_path != path:
                continue
            element = page.locator(selector).first
            expect(element).to_be_visible()
            for state in states:
                _in_state(page, element, state)
                value = legibility(element)
                floor = KNOWN_SHORTFALLS.get((settings.DEFAULT_SKIN, what, state), 3 if is_large(element) else 4.5)
                if value < floor:
                    shortfalls.append(f"{what} ({state}): {value:.2f} < {floor}")
    assert not shortfalls, f"in the {settings.DEFAULT_SKIN} skin: " + "; ".join(shortfalls)
