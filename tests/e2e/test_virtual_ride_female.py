"""A woman rides as one: her profile's word for her rider in Russian, and a woman's figure on the bike."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_virtual_ride import _trainer_in_its_menu

_SIGNED_IN = """async female => {
    const me = { authenticated: true, user_id: 1, female, page_url: '/ru/virtual-ride/',
        event_draft_url: '/ru/calendar/submit/draft/' };
    Site.get = async path => path === '/me' ? me : path === '/records' ? {} : path.startsWith('/rides') ? [] : {};
    Records.pull = async () => {};
    await Records.connect();
}"""
# how many parts a rider's model has: a woman's carries a bust and a ponytail the man's has not
_PARTS = "m => { let n = 0; m.g.traverse(o => { if (o.isMesh) n++; }); return n; }"


@pytest.mark.django_db(transaction=True)
def test_a_woman_s_profile_makes_her_rider_a_woman_in_the_menu_and_on_the_road(page: Page, live_server):
    _trainer_in_its_menu(page, live_server, lang="ru")
    title = page.locator("#hRider [data-t^='sec.rider']")
    expect(title).to_have_text(page.evaluate("t('sec.rider')"))
    his = page.evaluate(f"({_PARTS})(prev.model)")
    assert page.evaluate("prev.model.ch.female") is False
    page.evaluate(_SIGNED_IN, True)
    expect(title).to_have_text(page.evaluate("t('sec.riderF')"))
    assert page.evaluate("t('sec.riderF')") != page.evaluate("t('sec.rider')")
    expect(page.locator("#charPrev")).to_have_attribute("aria-label", page.evaluate("t('a11y.riderPreviewF')"))
    # the preview in the menu and the rider on the road are hers
    assert page.evaluate("[prev.model.ch.female, playerAvatar.ch.female]") == [True, True]
    assert page.evaluate(f"({_PARTS})(prev.model)") > his
    # a man's stays a man's
    page.evaluate(_SIGNED_IN, False)
    expect(title).to_have_text(page.evaluate("t('sec.rider')"))
    assert page.evaluate("[prev.model.ch.female, playerAvatar.ch.female]") == [False, False]


@pytest.mark.django_db(transaction=True)
def test_the_women_among_the_bots_and_the_members_ride_as_women(page: Page, live_server):
    _trainer_in_its_menu(page, live_server, lang="ru")
    women = page.evaluate("CHARS.filter(c => c.female).map(c => c.id)")
    assert set(women) == {"dana", "madina", "aliya", "saule", "zhanna", "kamila"}, women
    assert page.evaluate("makeRider(charById('dana')).ch.female") is True
    # a member whose profile says a woman, on the same route: drawn as one, named so without a name
    page.evaluate("() => { settings.mode = 'free'; settings.bots = 0; startRace(); }")
    page.wait_for_function("phase === 'countdown'", polling=100)
    named = page.evaluate(
        """() => {
            MP.riders = [{ user_id: 7, name: '', route: world.route.id, distance_m: me.s + 10, lane_m: 2, speed_ms: 8,
                power_w: 200, cadence_rpm: 90, age_s: 0, female: true }];
            mpSyncRemotes();
            const b = bots.find(x => x.remote && x.uid === 7);
            return [b.name, riderModels.get(b).ch.female];
        }"""
    )
    assert named == [page.evaluate("t('mp.riderF')"), True], named
