"""The colour theme a signed-in reader picks is kept in their profile, in every language."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session, open_navbar_if_collapsed


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_a_signed_in_choice_is_saved_and_kept_on_the_next_page(page: Page, live_server, language):
    member = User.objects.create_user(
        username="e2e_themer", email="e2e_themer@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/{language}/news/")
    open_navbar_if_collapsed(page)

    with page.expect_response(lambda r: r.request.method == "POST" and "/accounts/theme/" in r.url) as saved:
        page.locator("nav button[onclick='toggleTheme()']").click()
    assert saved.value.status == 200, saved.value.url
    member.refresh_from_db()
    assert member.theme == "dark"

    page.goto(f"{live_server.url}/{language}/calendar/list/")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
