"""E2E for handing a person without an account over (issue #438) -- to an account of their own, or to another
mentor: the link's way from the manager's card to the account, and back to the manager's answer."""

import datetime
import re

import pytest
from playwright.sync_api import Page, expect

from accounts import virtual_members
from accounts.models import ManagedMember, User, VirtualMember
from calendar_app.models import Competition
from registrations.models import CompetitionRegistration
from tests.e2e.conftest import UPCOMING, inject_session


def _member(username, first_name, last_name):
    return User.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password="testpass123!",
        role=User.Role.PARTICIPANT,
        first_name=first_name,
        last_name=last_name,
    )


def _sign_in(page, live_server, user):
    page.context.clear_cookies()
    inject_session(page, live_server, user)


@pytest.mark.django_db(transaction=True)
def test_a_person_goes_from_the_managers_card_into_their_own_account(page: Page, live_server):
    coach = _member("coach", "Ivan", "Petrov")
    virtual_members.consent(coach)
    kid = VirtualMember.objects.create(
        owner=coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
    )
    race = Competition.objects.create(
        title_ru="Transfer Race", date_start=UPCOMING, status=Competition.Status.APPROVED, registration_enabled=True
    )
    entry = CompetitionRegistration.objects.create(
        competition=race, virtual_member=kid, first_name="Dana", last_name="Kim", birth_date=kid.birth_date, gender="F"
    )
    dana = _member("dana", "Dana", "Kim")

    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    page.get_by_role("button", name="Hand over to the owner: Kim Dana").click()
    row = page.locator(f"#vm-{kid.pk}")
    link = row.locator("code").inner_text()
    assert re.search(r"/en/accounts/virtual-members/take/[0-9a-f-]{36}/$", link), link
    expect(row.locator(".share-btn")).to_have_attribute("data-share-url", link)

    _sign_in(page, live_server, dana)
    page.goto(link)
    expect(page.get_by_role("heading", level=1)).to_have_text("Take Kim Dana into your account?")
    keep = page.get_by_label("Let Ivan Petrov go on managing my registrations and photos")
    expect(keep).not_to_be_checked()
    keep.check()
    page.get_by_role("button", name="Take over").click()
    expect(page).to_have_url(re.compile(r"/en/accounts/profile/$"))
    expect(page.get_by_text("Your request is waiting for Ivan Petrov to accept it.")).to_be_visible()

    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    row = page.locator(f"#vm-{kid.pk}")
    expect(row).to_contain_text("Dana Kim asks to take Kim Dana into their account.")
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Confirm").click()
    expect(page.get_by_text("Kim Dana is now in the account of Dana Kim.")).to_be_visible()
    expect(page.locator(f"#vm-{kid.pk}")).to_have_count(0)
    entry.refresh_from_db()
    assert (entry.user_id, entry.virtual_member_id) == (dana.pk, None)
    assert ManagedMember.objects.filter(manager=coach, member=dana, accepted_at__isnull=False).exists()


@pytest.mark.django_db(transaction=True)
def test_a_person_goes_from_the_managers_card_to_another_mentor(page: Page, live_server):
    coach = _member("coach", "Ivan", "Petrov")
    virtual_members.consent(coach)
    kid = VirtualMember.objects.create(
        owner=coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
    )
    mentor = _member("mentor", "Olga", "Mentor")

    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    page.get_by_role("button", name="Hand over to a mentor: Kim Dana").click()
    row = page.locator(f"#vm-{kid.pk}")
    expect(row).to_contain_text("Link for a mentor")
    expect(row).to_contain_text("Send this link to the mentor who takes Kim Dana over")
    link = row.locator("code").inner_text()

    _sign_in(page, live_server, mentor)
    page.goto(link)
    expect(page.get_by_role("heading", level=1)).to_have_text("Become the mentor of Kim Dana?")
    page.get_by_label("I am authorized to handle their personal data").check()
    page.get_by_role("button", name="Accept").click()
    expect(page.get_by_text("Your request is waiting for Ivan Petrov to accept it.")).to_be_visible()

    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    row = page.locator(f"#vm-{kid.pk}")
    expect(row).to_contain_text("Olga Mentor asks to become the mentor of Kim Dana.")
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Confirm").click()
    expect(page.get_by_text("Kim Dana is now in the list of Olga Mentor.")).to_be_visible()
    expect(page.locator(f"#vm-{kid.pk}")).to_have_count(0)

    _sign_in(page, live_server, mentor)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    expect(page.locator(f"#vm-{kid.pk}")).to_contain_text("Kim Dana")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_the_two_ways_to_hand_over_stay_in_one_row_on_a_phone(page: Page, live_server, language):
    """A pair of buttons that belong together keeps one row at 360px, the words wrapping inside each, two lines
    at most; at 320px, the narrowest, nothing spills over a button's frame (the interface rules, 10)."""
    coach = _member("coach", "Ivan", "Petrov")
    virtual_members.consent(coach)
    kid = VirtualMember.objects.create(
        owner=coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
    )
    _sign_in(page, live_server, coach)
    shapes = {}
    for width in (360, 320):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(f"{live_server.url}/{language}/accounts/profile/")
        buttons = page.locator(f"#vm-{kid.pk} .virtual-transfer-kinds button")
        expect(buttons).to_have_count(2)
        shapes[width] = buttons.evaluate_all(
            """els => els.map(e => {
                const r = e.getBoundingClientRect(), s = getComputedStyle(e);
                const text = r.height - parseFloat(s.paddingTop) - parseFloat(s.paddingBottom) - 2;
                return {top: Math.round(r.top), height: Math.round(r.height),
                        lines: Math.round(text / parseFloat(s.lineHeight)), spills: e.scrollWidth > e.clientWidth};
            })"""
        )
    phone = shapes[360]
    assert phone[0]["top"] == phone[1]["top"] and phone[0]["height"] == phone[1]["height"], phone
    assert all(shape["lines"] <= 2 for shape in phone), phone
    assert not any(shape["spills"] for shape in shapes[360] + shapes[320]), shapes


@pytest.mark.django_db(transaction=True)
def test_a_live_link_is_named_for_whom_it_is_and_one_button_takes_it_back(page: Page, live_server):
    coach = _member("coach", "Ivan", "Petrov")
    virtual_members.consent(coach)
    kid = VirtualMember.objects.create(
        owner=coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
    )
    _sign_in(page, live_server, coach)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    row = page.locator(f"#vm-{kid.pk}")
    row.get_by_role("button", name="Hand over to the owner: Kim Dana").click()
    row = page.locator(f"#vm-{kid.pk}")
    expect(row).to_contain_text("Link for the owner")
    # One state at a time: while the link is live, it alone is on offer, and the hand-over buttons wait
    expect(row.get_by_role("button", name="Hand over to a mentor: Kim Dana")).to_have_count(0)
    page.once("dialog", lambda dialog: dialog.accept())
    # The page lands on the person's row by its anchor and scrolls there smoothly after it has loaded: a tap
    # aimed meanwhile lands wherever the scroll left the button (webkit, CI). The keyboard has no place to miss.
    row.get_by_role("button", name="Cancel the link: Kim Dana").press("Enter")
    row = page.locator(f"#vm-{kid.pk}")
    expect(row.get_by_role("button", name="Hand over to a mentor: Kim Dana")).to_be_visible()
    expect(row.locator("code")).to_have_count(0)
