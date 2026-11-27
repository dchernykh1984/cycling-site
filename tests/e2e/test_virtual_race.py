"""A virtual race with protocols on the trainer's page (specs/495-virtual-race): who drafts whom by its rules, the
route's control points and the crossings the page reports, the bib on the kit, what block 3 gathers in each mode,
and the phone told a heavy route may run slowly."""

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
    out_and_back = page.evaluate(_CROSSINGS, ["kyrbaltabay-tuganbay", 2])
    # a road out and back turned round at both ends is a loop: its far turn and its line each lap
    assert [(p, last) for _, p, last, _ in out_and_back["got"]] == [(1, False), (0, False), (1, False), (0, True)], (
        out_and_back
    )
    one_way = page.evaluate(_CROSSINGS, ["medeu", 3])
    # a route from one place to another is ridden once: its finish is its one point
    assert [(p, last) for _, p, last, _ in one_way["got"]] == [(0, True)], one_way


_A_RACE = """offset => {
    MP.offset = 0;
    const host = { user_id: 2, name: 'Organizer' };
    MP.groups = [{ id: 9, route: 'center', route_name: 'Center', host, is_host: false, is_member: true,
        members: [{ user_id: 1, name: 'Anna', bib: '51' }], cancelled: false, wind_ms: 0, wind_from_deg: 0,
        start_at: new Date(Date.now() + 2000).toISOString(),
        event: { id: 3, title: { ru: 'Zimnii kubok', kk: 'Qysqy kubok', en: 'Winter Cup' }, url: '/ru/calendar/3/' },
        mode: 'group', group_gap_s: 0,
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
            // the race's list on the page is the rider's own category's: a rider of another one rides other laps
            me.finishT = 100; const apart = raceList().length;
            const across = wakeOf(me, b); b.group = 'Women';
            return { bib: b.bib, cda: b.CdA, plate: !!plate, across, within: wakeOf(me, b), apart,
                     together: raceList().length };
        }"""
    )
    assert other["bib"] == "12" and other["cda"] == pytest.approx(0.41) and other["plate"], other
    assert other["across"] == 0 and other["within"] > 0.45, other
    assert (other["apart"], other["together"]) == (1, 2), other


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
    # the countdown runs to the rider's own start, the race's and a minute
    assert page.evaluate("groupRide.startAt - Date.parse(MP.groups[0].start_at)") == 60000


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
def test_block_three_gathers_what_the_mode_rides_together(page: Page, live_server):
    """A race with its settings at hand in race mode, a ride together in a free ride, nothing in a workout."""
    _trainer_in_its_menu(page, live_server)
    page.click("#modeSeg [data-mode='race']")
    expect(page.locator("#mpCreate")).to_have_text(page.evaluate("t('mp.create')"))
    expect(page.locator("#mpRaceOpts")).to_be_visible()  # no event to choose before them any more
    expect(page.locator("#mpRaceGapL")).to_be_visible()
    expect(page.locator("#mpRaceIntervalL")).to_be_hidden()
    page.select_option("#mpRaceMode", "itt")
    # a time trial: an interval between riders, and no drafting to choose
    expect(page.locator("#mpRaceIntervalL")).to_be_visible()
    expect(page.locator("#mpRaceGapL")).to_be_hidden()
    expect(page.locator("#mpRaceDraftL")).to_be_hidden()
    page.fill("#mpRaceInterval", "45")
    asked = page.evaluate("routeSel = 'center'; mpRace({ start_in_s: 120 })")
    assert {k: asked.get(k) for k in ("kind", "mode", "itt_interval_s", "loop", "start_in_s", "competition_id")} == {
        "kind": "race",
        "mode": "itt",
        "itt_interval_s": 45,
        "loop": True,
        "start_in_s": 120,
        "competition_id": None,
    }, asked
    for control in ("#mpRaceMode", "#mpRaceInterval"):
        box = page.locator(control).bounding_box()
        assert box and box["height"] >= 44, (control, box)
    # a race's event, with its registration on the site, is an organizer's to add: the calendar box
    page.select_option("#mpDelay", "at")
    expect(page.locator("#mpEventL")).to_be_hidden()
    page.evaluate("Records.me = Object.assign({}, Records.me, { organizes: true }); renderRaceOpts()")
    expect(page.locator("#mpEventL")).to_be_visible()
    # a free ride gathers a ride together: no race's settings, and anyone adds its event
    page.evaluate("Records.me = Object.assign({}, Records.me, { organizes: false })")
    page.click("#modeSeg [data-mode='free']")
    expect(page.locator("#mpCreate")).to_have_text(page.evaluate("t('mp.createRide')"))
    expect(page.locator("#mpRaceOpts")).to_be_hidden()
    expect(page.locator("#mpEventL")).to_be_visible()
    asked = page.evaluate("mpRace({ start_in_s: 120 })")
    assert asked["kind"] == "ride" and "mode" not in asked, asked
    # a workout gathers nothing: each rides their own plan, and the block says so and where to go instead -- but
    # the rides the member is in, a link's word and how things stand are still theirs to see
    page.click("#modeSeg [data-mode='plan']")
    expect(page.locator("#mpPlanNote")).to_have_text(page.evaluate("t('mp.planNote')"))
    for gathering in ("#mpCreate", "#mpRaceOpts", "#mpEventHint", "#mpHint"):
        expect(page.locator(gathering)).to_be_hidden()
    page.evaluate("mpNote('note')")
    for seen in ("#mpStatus", "#mpNote"):
        expect(page.locator(seen)).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_a_link_to_a_ride_switches_a_workout_to_its_mode_once_and_leaves_a_mode_chosen_after_it(
    page: Page, live_server
):
    """A member who opened a ride's link in a free ride and then picked a workout was flipped back by the next poll."""
    page.add_init_script("localStorage.setItem('alatau:settings', JSON.stringify({ mode: 'free' }))")
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en&group=7")
    page.wait_for_function("typeof mpFollowLink === 'function' && typeof LINKED !== 'undefined'")
    modes = page.evaluate(
        """() => {
            MP.groups = [{ id: 7, kind: 'ride', route: 'center', host: { user_id: 2, name: 'Anna' }, members: [] }];
            mpFollowLink(); const first = settings.mode;   // listed while the member rides free: theirs stays
            settings.mode = 'plan'; mpFollowLink();         // then a workout, picked after it
            return [first, settings.mode, MP.linkFollowed];
        }"""
    )
    assert modes == ["free", "plan", True], modes


@pytest.mark.django_db(transaction=True)
def test_the_calendar_box_is_kept_as_it_was_left_and_unticked_the_button_only_gathers(page: Page, live_server):
    """Two buttons, "Gather a ride" and "Add event", read as two ways of doing one thing: one button, and a box that
    sends its ride or race on to the event form -- left ticked or not as it was last time."""
    _trainer_in_its_menu(page, live_server)
    page.click("#modeSeg [data-mode='free']")
    page.select_option("#mpDelay", "at")
    expect(page.locator("#mpEventL")).to_have_text(page.evaluate("t('mp.eventOn')"))
    page.check("#mpEvent")
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#mpEvent")).to_be_checked()
    asked = page.evaluate(
        """() => {
            const asked = [];
            MP.status = 'on'; mpAction = (path, body) => asked.push('gather ' + path + ' ' + body.kind);
            mpAddEvent = () => asked.push('event form');
            settings.mode = 'free'; renderPlanEditor();
            $('#mpDelay').value = 'at'; renderWhen();
            mpCreateGroup();
            $('#mpEvent').checked = false; mpCreateGroup();
            $('#mpDelay').value = '60'; renderWhen(); $('#mpEvent').checked = true; mpCreateGroup();
            return asked;
        }"""
    )
    # ticked at a date and time: its event's form; unticked, or with a start minutes away, the ride alone
    assert asked == ["event form", "gather /groups ride", "gather /groups ride"], asked


@pytest.mark.django_db(transaction=True)
def test_a_card_tells_a_ride_from_a_race_and_a_time_trial_says_the_rider_s_own_start(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        """() => {
            const soon = new Date(Date.now() + 600e3).toISOString();
            const later = new Date(Date.now() + 7200e3).toISOString();
            const host = { user_id: 7, name: 'Anna' };
            MP.status = 'on';
            MP.groups = [
                { id: 1, route: 'center', start_at: soon, host, members: [host], kind: 'ride', mode: 'group' },
                { id: 2, route: 'center', start_at: later, host, members: [host], is_member: true, kind: 'race',
                  mode: 'itt', itt_interval_s: 30, me: { bib: '', group: '', laps: 1, start_offset_s: 60 } },
            ];
            renderMP();
        }"""
    )
    cards = page.locator("#mpGroups .mp-group")
    expect(cards.nth(0).locator("b")).to_contain_text("Anna is gathering a ride")
    expect(cards.nth(1).locator("b")).to_contain_text("Anna is gathering a race")
    expect(cards.nth(1).locator("small")).to_contain_text("Individual time trial. Your start 1:00 after the race's.")


@pytest.mark.django_db(transaction=True)
def test_a_race_card_names_its_event_and_each_rider_s_bib(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(_A_RACE, 0)
    page.evaluate("MP.status = 'on'; MP.groups[0].start_at = new Date(Date.now() + 600e3).toISOString(); renderMP()")
    card = page.locator("#mpGroups .mp-group small")
    # its event in the page's language, linked to the event's page in that language, out of the trainer's frame
    expect(card).to_contain_text("Event: Winter Cup.")
    link = card.get_by_role("link", name="Winter Cup")
    expect(link).to_have_attribute("href", "/en/calendar/3/")
    expect(link).to_have_attribute("target", "_top")
    expect(card).to_contain_text("Anna #51")
    expect(card).to_contain_text("Your bib 51, Women, laps: 3.")


@pytest.mark.django_db(transaction=True)
def test_a_phone_is_told_a_heavy_route_may_run_slowly(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    notice = page.locator("#startSum .heavy")
    coarse = page.evaluate("matchMedia('(pointer: coarse)').matches")
    page.evaluate("routeSel = 'granfondo'; renderStartSum()")
    # on this browser as it is: told only where the pointer is a finger
    expect(notice).to_have_count(1 if coarse else 0)
    page.evaluate(
        """() => {
            const real = matchMedia.bind(window);
            window.matchMedia = q => q === '(pointer: coarse)' ? { matches: true } : real(q);
        }"""
    )
    page.evaluate("renderStartSum()")
    expect(notice).to_have_text("May run slowly on a phone: many buildings and streets.")
    # a racetrack with a few buildings round it is not heavy
    page.evaluate("routeSel = 'sokol'; renderStartSum()")
    expect(notice).to_have_count(0)
