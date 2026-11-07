"""E2E for protocol sections (issue #452): on a phone, in every language, the organizer adds a section
named in all three and reads its number, every control on the page takes a tap and nothing scrolls
sideways, and the event's page shows each section's protocols under the section's own heading."""

import pytest
from django.utils.translation import gettext, override
from playwright.sync_api import Page, expect

from protocols.models import Protocol
from tests.e2e.conftest import inject_session

FINALS = {"ru": "Finaly", "kk": "Finaldar", "en": "Finals"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_on_a_phone_the_organizer_adds_a_section_and_the_event_shows_it(
    page: Page, live_server, organizer, approved_competition, lang
):
    inject_session(page, live_server, organizer)
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto(f"{live_server.url}/{lang}/protocols/event/{approved_competition.pk}/sections/")
    for code, name in FINALS.items():
        page.fill(f"#id_new-{code}", name)
    page.locator("button[value='add']").click()
    expect(page.locator("#section-2 h2")).to_contain_text(FINALS[lang])
    # The page the form returns to is measured once its styles are in, not while they arrive
    page.wait_for_load_state("load")

    assert page.evaluate("document.scrollingElement.scrollWidth <= document.scrollingElement.clientWidth")
    small = []
    for button in page.locator(".protocol-sections .btn").all():
        box = button.bounding_box()
        # to a tenth of a pixel: Firefox lays a 44 px line out as 43.99997
        if box and min(round(box["height"], 1), round(box["width"], 1)) < 44:
            small.append((button.inner_text(), box["width"], box["height"]))
    assert not small, small

    Protocol.objects.create(competition=approved_competition, protocol_type=Protocol.ProtocolType.ABSOLUTE)
    Protocol.objects.create(competition=approved_competition, protocol_type=Protocol.ProtocolType.GROUP, section=2)
    page.goto(f"{live_server.url}/{lang}/calendar/{approved_competition.pk}/")
    with override(lang):
        expected = [gettext("Protocols"), FINALS[lang]]
    expect(page.locator(".competition-protocol-heading")).to_have_text(expected)
