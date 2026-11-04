"""The owners' statistics in a browser (issue #184): a page a person opens counts itself, and the page of
statistics fits a phone and draws its charts, in the skin the suite runs in."""

import datetime

import pytest
from playwright.sync_api import Page

from accounts.models import User
from stats import counting
from stats.models import Tally
from tests.e2e.conftest import inject_session

# A browser as people have one: Playwright's own calls itself HeadlessChrome, which counts as a robot.
BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


@pytest.mark.browser_context_args(user_agent=BROWSER)
@pytest.mark.django_db(transaction=True)
def test_a_page_a_person_opens_counts_itself(page: Page, live_server):
    page.goto(f"{live_server.url}/ru/calendar/")
    # The page says it was opened as it loads, without waiting for an answer.
    page.wait_for_timeout(500)
    for _ in range(50):
        if Tally.objects.filter(dimension=Tally.Dimension.PAGE, key="/ru/calendar/").exists():
            break
        page.wait_for_timeout(200)
    pages = dict(Tally.objects.filter(dimension=Tally.Dimension.PAGE).values_list("key", "count"))
    assert pages == {"/ru/calendar/": 1}


@pytest.mark.django_db(transaction=True)
def test_the_statistics_fit_a_phone_and_draw_their_charts(page: Page, live_server):
    owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", role=User.Role.OWNER)
    today = counting.now().date()
    for back, views in enumerate((12, 30, 7)):
        day = today - datetime.timedelta(days=back)
        Tally.objects.create(day=day, dimension=Tally.Dimension.VIEWS, key=Tally.Audience.PEOPLE, count=views)
        Tally.objects.create(day=day, dimension=Tally.Dimension.BOT, key="search:Googlebot", count=views * 3)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 360, "height": 800})
    inject_session(page, live_server, owner)

    page.goto(f"{live_server.url}/kk/stats/?period=week")

    page.wait_for_function("[...document.querySelectorAll('canvas[data-chart]')].every(c => Chart.getChart(c))")
    assert page.locator("canvas[data-chart]").count() == 3
    assert page.evaluate("document.documentElement.scrollWidth") <= 360
    assert errors == []
