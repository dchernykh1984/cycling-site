"""Every skin keeps text readable: WCAG contrast of what reaches the screen, at rest and in use.

Runs in the skin the suite runs in (E2E_SKIN; light by default), so e2e.yml checks each skin.
"""

import pytest
from django.conf import settings
from django.utils import timezone
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import open_filter_panel, open_navbar_if_collapsed
from tests.e2e.contrast import is_large, legibility

# (page, what, selector, states)
CHECKS = [
    ("/ru/news/", "heading", "main h1", ("rest",)),
    ("/ru/news/", "news title", "main .card-title", ("rest",)),
    ("/ru/news/", "muted text", "main .card .text-muted", ("rest",)),
    ("/ru/news/", "brand", "nav .navbar-brand", ("rest", "hover")),
    ("/ru/news/", "navbar link", "nav .nav-link", ("rest", "hover", "focus")),
    ("/ru/news/", "share button", "main .share-btn", ("rest", "hover", "focus")),
    ("/ru/news/", "hint", "main .alert", ("rest",)),
    ("/ru/news/", "hint button", "main .alert .btn", ("rest", "hover", "focus")),
    ("/ru/news/", "footer", "footer", ("rest",)),
    ("/ru/news/", "footer link", "footer a", ("rest", "hover")),
    ("/ru/calendar/list/", "filter", "#et-btn-1", ("rest", "focus")),
    ("/ru/calendar/list/", "label", "main label", ("rest",)),
    ("/ru/calendar/list/", "list", "main :is(table td, .calendar-day-events li):visible", ("rest",)),
]

# Where the site's own themes already fall short: kept as they are, since light and dark are not
# to change, but never allowed to get worse. A designer's skin clears every check in full.
KNOWN_SHORTFALLS = {
    ("light", "muted text", "rest"): 3.8,
    ("dark", "footer link", "rest"): 3.8,
}


@pytest.fixture
def pages_with_content(db, organizer, race_event_type):
    """A news item and an event, and an event type so the type filter is live rather than disabled."""
    from news.models import NewsArticle

    NewsArticle.objects.create(title="Contrast news", intro="An intro in muted text.", body="<p>Body</p>")
    race = Competition.objects.create(
        title_ru="Contrast race",
        # Today in the site's zone: the unfiltered list holds the rest of this month, which a few
        # days ahead leaves in the month's last days.
        date_start=timezone.localdate(),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
    )
    race.event_types.add(race_event_type)


# The colours a state ends on, without the fade into it: WebKit may begin a button's fade only after
# the wait for its end below has looked, and a colour read mid-fade is neither state's.
NO_FADES = "*, *::before, *::after { transition: none !important; }"


def _in_state(page: Page, element, state):
    page.mouse.move(0, 0)
    if state == "hover":
        element.hover()
    elif state == "focus":
        element.focus()
    # Buttons fade between states; a colour read mid-fade is neither state's. A fade cut short by the
    # next state rejects its promise with AbortError, which only means it is over.
    element.evaluate("el => Promise.all(el.getAnimations().map(a => a.finished.catch(() => {})))")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", sorted({check[0] for check in CHECKS}))
def test_text_is_readable_in_this_skin(page: Page, live_server, pages_with_content, path):
    skin = settings.DEFAULT_SKIN
    page.goto(f"{live_server.url}{path}")
    page.add_style_tag(content=NO_FADES)
    # On a phone the menu and the filters fold away; open them to see what they look like.
    open_navbar_if_collapsed(page)
    open_filter_panel(page)
    shortfalls = []
    for check_path, what, selector, states in CHECKS:
        if check_path != path:
            continue
        element = page.locator(selector).first
        expect(element).to_be_visible()
        # WCAG leaves a disabled control out; one that should be live but is not is a broken fixture.
        expect(element).to_be_enabled()
        for state in states:
            _in_state(page, element, state)
            value = legibility(element)
            floor = KNOWN_SHORTFALLS.get((skin, what, state), 3 if is_large(element) else 4.5)
            if value < floor:
                shortfalls.append(f"{what} ({state}): {value:.2f} < {floor}")
    assert not shortfalls, f"in the {skin} skin: " + "; ".join(shortfalls)
