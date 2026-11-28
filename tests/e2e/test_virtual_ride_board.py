"""The riders nearby, in the ride's table: each with the gap to this rider and the power they ride at now."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_virtual_ride import _trainer_in_its_menu


@pytest.mark.django_db(transaction=True)
def test_the_table_of_riders_nearby_shows_each_one_s_power(page: Page, live_server):
    page.set_viewport_size({"width": 1280, "height": 800})
    _trainer_in_its_menu(page, live_server)
    page.click("#modeSeg [data-mode='race']")
    page.select_option("#bots", "3")
    page.evaluate("startRace()")
    page.wait_for_function("phase === 'countdown' && bots.length === 3", polling=100)
    page.evaluate(
        """() => {
            phase = 'race'; cdT = -1;
            bots.forEach((b, i) => { b.s = me.s + (i - 1) * 20; b.v = 10; });
            bots[0].name = 'A rider with a name long enough to be cut short';
            drawFrame(100);
            bots.forEach((b, i) => { b.P = 200 + 37 * i; }); updateHUD(readInput(), 0);
        }"""
    )
    rows = page.locator("#boardList li")
    expect(rows).to_have_count(4)
    unit = page.evaluate("t('u.w')")
    powers = page.evaluate("[...document.querySelectorAll('#boardList .pw')].map(e => e.textContent)")
    assert all(re.fullmatch(rf"\d+ {unit}", p) for p in powers), powers
    # the bots' as they ride, and this rider's own, from what drives them now
    assert {f"{200 + 37 * i} {unit}" for i in range(3)} <= set(powers), powers
    mine = page.locator("#boardList li.me .pw").text_content()
    assert mine == f"{round(page.evaluate('readInput().P'))} {unit}", mine
    # nothing spills out of a row: a long name is cut short, the power and the gap stay whole
    spilled = page.evaluate(
        "[...document.querySelectorAll('#boardList li')].filter(li => li.scrollWidth > li.clientWidth).length"
    )
    assert spilled == 0
    # a rider who finished rides at no power
    page.evaluate("() => { bots[1].finishT = 100; updateHUD(readInput(), 0); }")
    assert "" in page.evaluate("[...document.querySelectorAll('#boardList .pw')].map(e => e.textContent)")
