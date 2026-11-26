"""A virtual race with protocols on the trainer's page (specs/495-virtual-race): who drafts whom by its rules, the
route's control points and the crossings the page reports, the bib on the kit and the race's settings for an
event."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_virtual_ride import _STILL, _ride_alone, _trainer_in_its_menu


def test_a_time_trial_has_no_wake_and_categories_draft_each_other_only_when_the_maker_allows(page: Page):
    errors = _ride_alone(page)
    shares = page.evaluate(
        f"""() => {{
            globalThis.mpStepRemote = () => {{}};
            const ahead = newRider('ahead', 0, 75, me.s + 1.71 + .7, me.lane); ahead.remote = true; ahead.CdA = me.CdA;
            bots = [ahead]; me.group = 'Women';
            const share = (race, group) => {{
                globalThis.groupRide = race && {{ gid: 9, race }}; ahead.group = group;
                stepRide(1 / 60, {_STILL}, 0); return me.draft;
            }};
            return [
                share(null, 'Elite'),                                         // a group ride without an event
                share({{ mode: 'itt', draftBetween: true }}, 'Women'),         // a time trial: nobody's wake
                share({{ mode: 'group', draftBetween: false }}, 'Elite'),      // another category, not allowed
                share({{ mode: 'group', draftBetween: false }}, 'Women'),      // one's own category
                share({{ mode: 'group', draftBetween: true }}, 'Elite'),       // another category, allowed
            ];
        }}"""
    )
    assert shares == pytest.approx([0.45, 0, 0, 0.45, 0.45], abs=1e-3)
    assert errors == [], errors


def _routes(page: Page, live_server) -> None:
    """The trainer's page with its maps: the courses are built without drawing them."""
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildCourse === 'function'")


@pytest.mark.django_db(transaction=True)
def test_a_route_s_control_points_are_its_turns_back(page: Page, live_server):
    _routes(page, live_server)
    points = page.evaluate(
        """() => Object.fromEntries(['granfondo', 'kyrbaltabay-tuganbay', 'sokol', 'center'].map(id => {
            const T = buildCourse(ROUTES.find(r => r.id === id)).T;
            return [id, turnPoints(T).map(Math.round)];
        }))"""
    )
    # Granfondo 2026 turns back twice, the second the smooth turn by Vostochka on Al-Farabi; an out-and-back turns
    # at its far end; a racetrack's hairpin and a city loop's corners are no turns back
    assert len(points["granfondo"]) == 2 and points["granfondo"] == pytest.approx([1446, 8920], abs=60), points
    assert len(points["kyrbaltabay-tuganbay"]) == 1, points
    assert points["sokol"] == [] and points["center"] == [], points


_CROSSINGS = """([id, laps]) => {
    MP.offset = 0; MP.crossings = [];
    world = buildCourse(ROUTES.find(r => r.id === id));
    groupRide = { gid: 9, race: { mode: 'group', draftBetween: true, me: { bib: '51', group: 'Women', laps } } };
    if (world.T.loop) world.FIN = world.S0 + laps * world.T.L;
    const before = Date.now();
    for (let s = world.S0; s < world.FIN + 50; s += 7) raceCrossings(s, s + 7, .5);
    const after = Date.now(), turns = turnPoints(world.T);
    return { turns: turns.length, after, before,
             got: MP.crossings.map(c => [c.gid, c.point, c.last, c.at_ms]) };
}"""


@pytest.mark.django_db(transaction=True)
def test_a_race_reports_each_lap_and_turn_once_and_its_last_lap_as_the_finish(page: Page, live_server):
    _routes(page, live_server)
    loop = page.evaluate(_CROSSINGS, ["granfondo", 2])
    # two laps of a loop with two turns: each turn and the line once a lap, the second lap's line the finish
    assert [(g, p, last) for g, p, last, _ in loop["got"]] == [
        (9, 1, False),
        (9, 2, False),
        (9, 0, False),
        (9, 1, False),
        (9, 2, False),
        (9, 0, True),
    ], loop
    # at the moment each happened, on the site's clock
    assert all(loop["before"] - 1000 <= at <= loop["after"] for *_, at in loop["got"]), loop
    out_and_back = page.evaluate(_CROSSINGS, ["kyrbaltabay-tuganbay", 3])
    # a route out and back is ridden once: its turn, then its finish
    assert [(p, last) for _, p, last, _ in out_and_back["got"]] == [(1, False), (0, True)], out_and_back


_A_RACE = """offset => {
    MP.offset = 0;
    const host = { user_id: 2, name: 'Organizer' };
    MP.groups = [{ id: 9, route: 'center', route_name: 'Center', host, is_host: false, is_member: true,
        members: [{ user_id: 1, name: 'Anna', bib: '51' }], cancelled: false, wind_ms: 0, wind_from_deg: 0,
        start_at: new Date(Date.now() + 2000).toISOString(),
        event: { id: 3, title: 'Winter Cup', url: '/en/calendar/3/' }, mode: 'group', group_gap_s: 0,
        itt_interval_s: 30, draft_between_groups: false, loop: true,
        me: { bib: '51', group: 'Women', laps: 3, start_offset_s: offset } }];
}"""


@pytest.mark.django_db(transaction=True)
def test_a_race_rider_wears_their_bib_and_rides_their_category_s_laps(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(_A_RACE, 0)
    page.evaluate("mpMaybeStart()")
    page.wait_for_function("phase === 'countdown'", polling=100)
    ridden = page.evaluate(
        """() => ({ laps: (world.FIN - world.S0) / world.T.L, bib: me.bib, group: me.group,
                    plate: !!playerAvatar.g.getObjectByName('bib') })"""
    )
    assert ridden == {"laps": pytest.approx(3), "bib": "51", "group": "Women", "plate": True}, ridden
    # a rider of another category beside them: their bib on their back, their size kept, and no wake, as the
    # race's maker chose
    other = page.evaluate(
        """() => {
            MP.riders = [{ user_id: 5, name: 'Boris', route: 'center', status: 'ride', mode: 'race', group_id: 9,
                distance_m: me.s + 2.41, speed_ms: 0, cadence_rpm: 0, power_w: 0, lane_m: me.lane,
                finished_s: null, age_s: 0, cda: .41, bib: '12', group: 'Elite' }];
            mpSyncRemotes();
            const b = bots.find(x => x.remote), plate = riderModels.get(b).g.getObjectByName('bib');
            const across = wakeOf(me, b); b.group = 'Women';
            return { bib: b.bib, cda: b.CdA, plate: !!plate, across, within: wakeOf(me, b) };
        }"""
    )
    assert other["bib"] == "12" and other["cda"] == pytest.approx(0.41) and other["plate"], other
    assert other["across"] == 0 and other["within"] > 0.45, other


@pytest.mark.django_db(transaction=True)
def test_a_time_trial_rider_starts_at_their_own_time(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(_A_RACE, 60)
    page.evaluate("mpMaybeStart()")
    page.wait_for_timeout(300)
    # a minute after the race's start: still waiting in the menu
    assert page.evaluate("phase") == "menu"
    page.evaluate("MP.groups[0].start_at = new Date(Date.now() - 58000).toISOString(); mpMaybeStart()")
    page.wait_for_function("phase === 'countdown'", polling=100)
    assert page.evaluate("cdT") == pytest.approx(2, abs=0.5)


@pytest.mark.django_db(transaction=True)
def test_crossings_left_over_go_from_the_menu_with_their_race_and_are_sent_once(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    sent = page.evaluate(
        """async () => {
            const bodies = [];
            Site.post = async (path, body) => {
                bodies.push(body);
                return { server_now: new Date().toISOString(), online: [], groups: [], riders: [] };
            };
            MP.status = 'on'; MP.crossings = [{ gid: 9, point: 0, at_ms: Date.now() - 500, last: true }];
            await mpPoll(); await mpPoll();
            clearTimeout(MP.timer); MP.status = 'off';
            return { bodies, left: MP.crossings.length };
        }"""
    )
    first, second = sent["bodies"]
    # the finish the rider rode before going back to the menu, with its race, and nothing of the page's own queue
    assert first["status"] == "lobby" and first["group_id"] == 9, first
    assert [set(c) for c in first["crossings"]] == [{"point", "at_ms", "last"}], first
    assert "crossings" not in second and sent["left"] == 0, sent


@pytest.mark.django_db(transaction=True)
def test_an_organizer_sets_a_race_up_for_their_event(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#mpRaceBox")).to_be_hidden()  # a member without events of their own sees nothing of it
    page.evaluate(
        """async () => {
            Site.get = async path => path === '/events'
                ? [{ id: 3, title: 'Winter Cup', url: '/en/calendar/3/', date_start: '2026-12-20' }] : [];
            await mpLoadEvents();
        }"""
    )
    expect(page.locator("#mpRaceBox")).to_be_visible()
    expect(page.locator("#mpRaceOpts")).to_be_hidden()
    page.select_option("#mpRaceEvent", "3")
    expect(page.locator("#mpRaceOpts")).to_be_visible()
    expect(page.locator("#mpRaceGapL")).to_be_visible()
    expect(page.locator("#mpRaceIntervalL")).to_be_hidden()
    page.select_option("#mpRaceMode", "itt")
    # a time trial: an interval between riders, and no drafting to choose
    expect(page.locator("#mpRaceIntervalL")).to_be_visible()
    expect(page.locator("#mpRaceGapL")).to_be_hidden()
    expect(page.locator("#mpRaceDraftL")).to_be_hidden()
    page.fill("#mpRaceInterval", "45")
    asked = page.evaluate("routeSel = 'center'; mpRace({ start_in_s: 120 })")
    assert {k: asked[k] for k in ("competition_id", "mode", "itt_interval_s", "loop", "start_in_s")} == {
        "competition_id": 3,
        "mode": "itt",
        "itt_interval_s": 45,
        "loop": True,
        "start_in_s": 120,
    }, asked
    # a race for a date and time: the event is there already, so no new event is offered for it
    page.select_option("#mpDelay", "at")
    expect(page.locator("#mpEvent")).to_be_hidden()
    page.select_option("#mpRaceEvent", "")
    expect(page.locator("#mpEvent")).to_be_visible()
    assert "competition_id" not in page.evaluate("mpRace({ start_in_s: 120 })")
    page.select_option("#mpRaceEvent", "3")
    for control in ("#mpRaceEvent", "#mpRaceMode", "#mpRaceInterval"):
        box = page.locator(control).bounding_box()
        assert box and box["height"] >= 44, (control, box)


@pytest.mark.django_db(transaction=True)
def test_a_race_card_names_its_event_and_each_rider_s_bib(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(_A_RACE, 0)
    page.evaluate("MP.status = 'on'; MP.groups[0].start_at = new Date(Date.now() + 600e3).toISOString(); renderMP()")
    card = page.locator("#mpGroups .mp-group small")
    expect(card).to_contain_text("Event: Winter Cup.")
    expect(card).to_contain_text("Anna #51")
    expect(card).to_contain_text("Your bib 51, Women, laps: 3.")
