"""Strava live segments on the virtual ride: a member's starred segment on the route, raced against their own times."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_virtual_ride import _trainer_in_its_menu

SEG_STEP = 4  # js/segments.js's SEG_STEP_M: how finely the route is searched for a segment's ends
MINUS = chr(0x2212)  # the gap's sign, as the window writes it

# A route's own line from `a` to `b` metres along it, as Strava gives a segment's: [[lat, lon, height, metres], ...]
_LINE = """(T, a, b) => {
    const o = {}, points = [];
    for (let s = a; s <= b; s += 20) {
        sampleAt(T, s, o); const ll = unproj(o.x, o.z, T.origin);
        points.push([ll.lat, ll.lon, o.y, s - a]);
    }
    return points;
}"""
# A segment of that line with the member's three efforts on it and the best one's even pace; Site's reads of it
# answered in the page, as the site would answer them from Strava.
_STUB = (
    """({ route, a, b }) => {
    const T = buildTrack(ROUTES.find(r => r.id === route)), L = b - a, points = ("""
    + _LINE
    + """)(T, a, b);
    const first = points[0], last = points[points.length - 1];
    window.SEG = { id: 9, name: 'Test climb', distance_m: L, average_grade: 3,
        start: first.slice(0, 2), end: last.slice(0, 2), pr_s: 120 };
    window.SEG_DETAIL = { id: 9, distance_m: L, points, efforts: [120, 130, 150],
        best: { elapsed_s: 120, date: '2026-06-01', times: [[0, 0], [L, 120]] } };
    Records.me = { authenticated: true, user_id: 1, strava_available: true, strava_segments: true,
        strava_segments_url: '/en/virtual-ride/strava/connect/?segments=1' };
    const get = Site.get.bind(Site);
    Site.get = p => p === '/strava/segments' ? Promise.resolve([SEG])
        : p === '/strava/segments/9' ? Promise.resolve(SEG_DETAIL) : get(p);
}"""
)
# the rider rides on at 10 m/s, a metre a step, to `upto` metres along the route or until the try is over
_RIDE_ON = """upto => {
    let s = me.s;
    while (Segs.on[0].run && s < upto) {
        const to = Math.min(upto, s + 1); Segs.step(s, to, (to - s) / 10, { P: 250 }); s = to;
    }
    me.s = s; segHUD();
}"""


@pytest.mark.django_db(transaction=True)
def test_a_starred_segment_on_the_route_is_timed_from_its_start_to_its_end_against_the_best_effort(
    page: Page, live_server
):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(_STUB, {"route": "farabi", "a": 800, "b": 1800})
    page.locator("#segOn").check()
    page.evaluate("() => { pickRoute('farabi'); settings.mode = 'free'; startRace(); }")
    page.wait_for_function("phase === 'countdown' && Segs.on.length === 1", polling=100)
    placed = page.evaluate("() => [Segs.on[0].s0, Segs.on[0].len]")
    assert placed[0] == pytest.approx(800, abs=SEG_STEP) and placed[1] == pytest.approx(1000, abs=2 * SEG_STEP), placed
    # 300 m before it the window says it is coming, with the best time
    page.evaluate("() => { phase = 'race'; me.s = Segs.on[0].s0 - 300; segHUD(); }")
    box = page.locator("#segBox")
    expect(box).to_be_visible()
    expect(box.locator("#segName")).to_have_text("Test climb")
    expect(box).to_contain_text(page.evaluate("t('seg.soon')"))
    expect(box).to_contain_text("2:00")
    # the ride itself crosses its start: the try begins
    page.evaluate("() => { me.s = Segs.on[0].s0 - .3; me.v = 10; drawFrame(100); drawFrame(100); }")
    assert page.evaluate("!!Segs.on[0].run"), "the ride crossed the segment's start without starting a try"
    # halfway at 10 m/s: 50 s for what the best effort took 60 s, so 10 s ahead of it, green
    page.evaluate(f"({_RIDE_ON})(Segs.on[0].run.at + Segs.on[0].len / 2)")
    assert page.evaluate("Math.round(Segs.on[0].run.t)") == 50
    expect(box.locator("#segRows .ahead dd").first).to_have_text(f"{MINUS}0:10")
    expect(box.locator("canvas#segProf")).to_be_visible()
    # on to its end: 100 s against 120, the best now, said and shown with its place among the member's efforts
    page.evaluate(f"({_RIDE_ON})(Infinity)")
    result = page.evaluate("() => [Math.round(Segs.result.t), Segs.result.place, Segs.result.of]")
    assert result == [100, 1, 4], result
    said = page.evaluate("t('seg.doneFaster', { name: 'Test climb', t: '1:40', d: '0:20' })")
    expect(page.locator("#toast")).to_have_text(said)
    expect(box).to_contain_text(page.evaluate("t('seg.finished')"))
    expect(box).to_contain_text(page.evaluate("t('seg.placeOf', { p: 1, n: 4 })"))


@pytest.mark.django_db(transaction=True)
def test_a_segment_on_a_road_ridden_both_ways_is_raced_only_the_way_it_runs(page: Page, live_server):
    """Kyrbaltabay-Tuganbay goes out and comes back on one road: a segment of its way back is not its way out."""
    _trainer_in_its_menu(page, live_server)
    starts, way_back = page.evaluate(
        """() => {
            const T = buildTrack(ROUTES.find(x => x.id === 'kyrbaltabay-tuganbay')), a = T.L * .75;
            const points = ("""
        + _LINE
        + """)(T, a, a + 1000);
            return [segPlaces(T, { distance_m: 1000, points }).map(p => Math.round(p.s0)), Math.round(a)];
        }"""
    )
    assert len(starts) == 1 and abs(starts[0] - way_back) <= SEG_STEP, (starts, way_back)


@pytest.mark.django_db(transaction=True)
def test_the_live_segments_box_opens_its_fields_keeps_them_and_asks_for_strava_s_permission(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#segHint")).to_have_text(page.evaluate("t('seg.hint')"))
    expect(page.locator("#segOpts")).to_be_hidden()
    page.evaluate(
        "() => { Records.me = { authenticated: true, user_id: 1, strava_available: true, strava_segments: false,"
        " strava_segments_url: '/ru/virtual-ride/strava/connect/?segments=1' }; }"
    )
    page.locator("#segOn").check()
    expect(page.locator("#segOpts")).to_be_visible()
    # every field a box, on as a member who has not chosen finds them
    expect(page.locator("#segFields input")).to_have_count(page.evaluate("SEG_FIELDS.length"))
    ticked = page.evaluate("[...document.querySelectorAll('#segFields input')].map(i => i.checked)")
    assert ticked == page.evaluate("SEG_FIELDS.map(f => f[2])"), ticked
    # Strava's permission first, asked at Strava for the segments and back to the page
    link = page.locator("#segState a")
    expect(link).to_have_text(page.evaluate("t('seg.allowLink')"))
    expect(link).to_have_attribute("href", re.compile(r"^/en/virtual-ride/strava/connect/\?segments=1&next="))
    page.locator('#segFields input[data-seg="power"]').check()
    page.locator('#segFields input[data-seg="profile"]').uncheck()
    kept = json.loads(page.evaluate("localStorage.getItem('alatau:settings')"))["segments"]
    assert kept["on"] and kept["fields"]["power"] and not kept["fields"]["profile"], kept
    # off again, its fields fold away and stay as chosen
    page.locator("#segOn").uncheck()
    expect(page.locator("#segOpts")).to_be_hidden()
    assert page.evaluate("settings.segments.fields.power === true && settings.segments.on === false")
