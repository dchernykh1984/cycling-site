"""Published results stand out in both themes, on desktop and mobile."""

import datetime
import re

import pytest
from django.urls import reverse
from django.utils.translation import gettext, override
from playwright.sync_api import Page, expect

from calendar_app.models import CompetitionMaterial
from protocols.models import Protocol
from tests.e2e.conftest import UPCOMING
from tests.language_urls import in_language


def _contrast(first, second):
    def luminance(colour):
        channels = [int(value) / 255 for value in re.findall(r"\d+", colour)[:3]]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _appearance(link):
    return link.evaluate(
        "el => { const s = getComputedStyle(el); return {fill: s.backgroundColor, text: s.color,"
        " weight: parseInt(s.fontWeight), body: getComputedStyle(document.body).backgroundColor}; }"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["ru", "kk", "en"])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("source", ["url", "file"])
def test_published_result_links_are_filled_bold_and_legible(
    page: Page, live_server, approved_competition, language, theme, source
):
    comp = approved_competition
    # Publication, rather than the event date, controls emphasis: live results can appear early.
    comp.date_start = UPCOMING
    if source == "url":
        comp.url_results = "https://example.com/results"
        result_url = comp.url_results
    else:
        comp.file_results = "competitions/results.pdf"
        result_url = comp.file_results.url
    comp.save()
    live = Protocol.objects.create(competition=comp, protocol_type="absolute", is_live=True, stage_label="Stage 1")
    final = Protocol.objects.create(competition=comp, protocol_type="group", is_live=False)
    CompetitionMaterial.objects.create(competition=comp, title="Photos", url="https://example.com/photos")

    page.goto(f"{live_server.url}/{language}/calendar/{comp.pk}/")
    page.evaluate("theme => document.documentElement.setAttribute('data-bs-theme', theme)", theme)
    with override(language):
        heading = page.get_by_role("heading", name=gettext("Protocols"), exact=True)
        materials_heading = page.get_by_role("heading", name=gettext("Additional materials"), exact=True)
        live_label = gettext("Live")
    expect(heading).to_be_visible()
    assert int(heading.evaluate("el => getComputedStyle(el).fontWeight")) >= 700
    assert float(heading.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")) > float(
        materials_heading.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")
    )
    live_link = page.locator(f"a[href='{in_language(reverse('protocol_detail', args=[live.pk]), language)}']")
    final_link = page.locator(f"a[href='{in_language(reverse('protocol_detail', args=[final.pk]), language)}']")
    expect(live_link.locator(".badge")).to_have_text(live_label)
    expect(final_link.locator(".badge")).to_have_count(0)
    for link in (page.locator(f"a[href='{result_url}']"), live_link, final_link):
        expect(link).to_be_visible()
        for state in ("rest", "hover", "focus"):
            if state == "hover":
                link.hover()
            elif state == "focus":
                page.mouse.move(0, 0)
                link.focus()
            style = _appearance(link)
            assert style["fill"] != "rgba(0, 0, 0, 0)", (theme, state, style)
            assert _contrast(style["fill"], style["body"]) >= 3, (theme, state, style)
            assert _contrast(style["text"], style["fill"]) >= 4.5, (theme, state, style)
            assert style["weight"] >= 700
        box = link.bounding_box()
        assert box is not None
        assert box["x"] >= -1 and box["x"] + box["width"] <= page.evaluate("window.innerWidth") + 1
    expect(page.get_by_role("link", name="Photos", exact=True)).to_have_css("background-color", "rgba(0, 0, 0, 0)")


@pytest.mark.django_db(transaction=True)
def test_a_past_event_without_results_has_no_result_buttons(page: Page, live_server, approved_competition):
    approved_competition.date_start = UPCOMING - datetime.timedelta(days=100)
    approved_competition.save()
    page.goto(f"{live_server.url}/en/calendar/{approved_competition.pk}/")
    expect(page.get_by_role("link", name="Results", exact=True)).to_have_count(0)
    expect(page.get_by_role("heading", name="Protocols", exact=True)).to_have_count(0)
