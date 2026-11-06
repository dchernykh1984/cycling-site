"""Record labels render independently of WebGL and external trainer sensors."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from api.endpoints.virtual_ride import PresenceIn
from tests import trainer_page
from tests.e2e.conftest import inject_session
from tests.e2e.test_interface_rules import _REACH


def _language_block(source: str) -> str:
    """The page's words and t(), to run the renderers below in the page's own words (Russian here)."""
    start = source.index("const TEXT_RU = ")
    return source[start : source.index("const fmt1 = ", start)]


@pytest.mark.parametrize("demo", [False, True])
def test_a_route_record_keeps_its_date_and_demo_label(page: Page, demo: bool):
    source = _trainer_source()
    function = re.search(r"function renderRecords\(\) \{.*?^\}", source, re.DOTALL | re.MULTILINE)
    assert function is not None
    # Exercise the shipped DOM renderer without depending on a GPU, CDN or Bluetooth.
    page.set_content(
        '<div id="recSync"></div><div id="recTotals"></div><div id="recPeaks"></div>'
        '<div id="recRoutes"></div><div id="recHist"></div><button id="btnRecReset"></button>'
    )
    page.evaluate(
        """({words, render, demo}) => {
            const $ = s => document.querySelector(s);
            const ROUTES = [{id: 'center', name: 'Center'}], PEAKS = [];
            const fmtDate = () => 'DATE', fmtTime = String, fmt1 = String, routeName = String;
            const Records = {synced: false, data: {
                routes: {center: {time: 120, date: 1, attempts: 2, demo}},
                peaks: {}, totals: {rides: 2, dist: 4, gain: 1, time: 240}, history: []
            }};
            eval(words + render + '; renderRecords();');
        }""",
        {"words": _language_block(source), "render": function.group(), "demo": demo},
    )
    label = "DATE" + (", \u0434\u0435\u043c\u043e" if demo else "") + ", \u043f\u043e\u043f\u044b\u0442\u043e\u043a: 2"
    expect(page.locator("#recRoutes small")).to_have_text(label)


def _cut(source: str, pattern: str) -> str:
    found = re.search(pattern, source, re.DOTALL | re.MULTILINE)
    assert found is not None, pattern
    return found.group()


def _trainer_source() -> str:
    return trainer_page.source()


def test_riding_again_after_a_group_race_rides_alone(page: Page):
    handler = re.search(r"^\$\('#btnAgain'\)\.onclick = .*$", _trainer_source(), re.MULTILINE)
    assert handler is not None
    page.set_content('<div id="resM"></div><button id="btnAgain"></button>')
    page.evaluate(
        """handler => {
            const $ = s => document.querySelector(s);
            let groupRide = {gid: 7, startAt: 0};
            const startRace = () => { window.rodeIn = groupRide; };
            eval(handler);
        }""",
        handler.group(),
    )
    page.click("#btnAgain")
    # The race is over: riding again must not report a second finish into it.
    assert page.evaluate("window.rodeIn") is None


def test_a_group_race_card_keeps_its_button_while_the_lobby_ticks(page: Page):
    source = _trainer_source()
    function = re.search(r"^function renderMP\(\) \{.*?^\}", source, re.DOTALL | re.MULTILINE)
    assert function is not None
    page.set_content(
        '<p id="mpStatus"></p><div id="mpOnline"></div><div id="mpGroups"></div><button id="mpCreate"></button>'
    )
    page.evaluate(
        """({words, render}) => {
            const $ = s => document.querySelector(s);
            const host = {user_id: 1, name: 'Anna'};
            window.MP = {status: 'on', online: [], groups: [
                {id: 7, route: 'center', route_name: 'Center', host, members: [host], is_host: false, is_member: false}
            ]};
            const Records = {me: {user_id: 2}}, mpStartLocal = () => Date.now() + 60000, LINKED = null;
            const fmtTime = String, routeName = String, routeTitle = g => g.route_name, hexs = String, mpColor = String;
            const mpMyGroup = () => null, renderStartSum = () => {}, mpAction = path => { window.asked = path; };
            eval(words + render);
            window.renderMP = renderMP;
            renderMP();
        }""",
        {"words": _language_block(source), "render": function.group()},
    )
    button = page.locator("#mpGroups button.act").element_handle()
    page.evaluate("renderMP()")  # the lobby's countdown redraws every second
    # A tap that lands between two redraws reaches the same button.
    assert button.evaluate("b => b.isConnected")
    button.click()
    assert page.evaluate("window.asked") == "/groups/7/join"
    page.evaluate("MP.groups = []; renderMP()")
    expect(page.locator("#mpGroups > *")).to_have_count(0)


@pytest.mark.django_db(transaction=True)
def test_the_profile_link_to_the_ride_is_big_enough_to_tap(page: Page, live_server):
    member = User.objects.create_user(
        username="e2e_vr", email="e2e_vr@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/kk/accounts/profile/")
    link = page.locator("#virtual-rides .card-header a")
    link.scroll_into_view_if_needed()  # a tap is measured where it can land: on screen
    wide, high = link.evaluate(_REACH)
    assert wide >= 44 and high >= 44, (wide, high)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["kk", "en"])
def test_the_trainer_speaks_the_language_of_the_page(page: Page, live_server, lang: str):
    page.goto(f"{live_server.url}/{lang}/virtual-ride/")
    frame = page.frame_locator("iframe.virtual-ride-frame")
    expect(frame.locator("html")).to_have_attribute("lang", lang)
    words = frame.locator("html").evaluate("() => [TEXT[LANG].start, TEXT.ru.start, TEXT[LANG]['sec.route']]")
    assert words[0] != words[1]
    expect(frame.locator("#btnStart")).to_have_text(words[0])
    expect(frame.locator("#hRoute")).to_contain_text(words[2])


@pytest.mark.django_db(transaction=True)
def test_a_link_to_a_group_race_reaches_the_framed_trainer(page: Page, live_server):
    page.goto(f"{live_server.url}/en/virtual-ride/?group=5")
    frame = page.frame_locator("iframe.virtual-ride-frame").locator("html")
    expect(frame).to_have_attribute("lang", "en")
    linked, link, back = frame.evaluate(
        "() => [LINKED, groupLink(5), decodeURIComponent(Site.loginHref().split('next=')[1])]"
    )
    # the race the link named, a link to share that opens the site's page, and a sign-in that returns to it
    assert (linked, link, back) == (5, f"{live_server.url}/en/virtual-ride/?group=5", "/en/virtual-ride/?group=5")


def test_a_linked_group_race_stands_out_and_its_link_can_be_copied(page: Page):
    source = _trainer_source()
    pieces = [
        _cut(source, pattern)
        for pattern in (
            r"^function renderMP\(\) \{.*?^\}",
            r"^function mpNote\(text\) \{.*?\}$",
            r"^async function mpShare\(g\) \{.*?^\}",
        )
    ]
    page.set_content(
        '<p id="mpStatus"></p><div id="mpOnline"></div><div id="mpGroups"></div><button id="mpCreate"></button>'
        '<p id="mpNote" class="hidden"></p>'
    )
    page.evaluate(
        """({words, code}) => {
            Object.defineProperty(navigator, 'share', {value: undefined, configurable: true});
            Object.defineProperty(navigator, 'clipboard', {value: {writeText: async url => { window.copied = url; }}});
            const $ = s => document.querySelector(s);
            const host = {user_id: 1, name: 'Anna'}, LINKED = 7;
            window.MP = {status: 'on', online: [], groups: [
                {id: 7, route: 'center', route_name: 'Center', host, members: [host], is_host: false, is_member: false},
                {id: 8, route: 'center', route_name: 'Center', host, members: [host], is_host: false, is_member: false}
            ]};
            const Records = {me: {user_id: 2}}, mpStartLocal = () => Date.now() + 60000, groupLink = id => 'LINK-' + id;
            const fmtTime = String, routeName = String, routeTitle = g => g.route_name, hexs = String, mpColor = String;
            const mpMyGroup = () => null, renderStartSum = () => {}, mpAction = () => {};
            eval(words + code);
            window.t = t;
            renderMP();
        }""",
        {"words": _language_block(source), "code": "\n".join(pieces)},
    )
    linked = page.locator('#mpGroups [data-gid="7"]')
    expect(linked).to_have_class(re.compile(r"\blinked\b"))
    expect(page.locator('#mpGroups [data-gid="8"]')).not_to_have_class(re.compile(r"\blinked\b"))
    # the mark is said in words, not only by the frame's colour
    expect(linked.locator("small")).to_contain_text(page.evaluate("t('mp.byLink').trim()"))
    linked.get_by_role("button", name=page.evaluate("t('mp.share')")).click()
    expect(page.locator("#mpNote")).to_have_text(page.evaluate("t('mp.copied', {url: 'LINK-7'})"))
    assert page.evaluate("window.copied") == "LINK-7"


@pytest.mark.parametrize("connected", [False, True])
def test_the_setup_page_offers_strava_or_says_the_rides_go_there(page: Page, connected: bool):
    source = _trainer_source()
    note = _cut(source, r"^function renderStravaNote\(\) \{.*?^\}")
    page.set_content('<style>.hidden{display:none}</style><p id="stravaNote" class="hidden"></p>')
    page.evaluate(
        """({words, note, connected}) => {
            const $ = s => document.querySelector(s);
            const STRAVA_LOGO = '', topPath = () => '/ru/virtual-ride/?group=5';
            const Records = {accountUrl: '/kk/accounts/profile/', me: {authenticated: true, strava_available: true,
                strava_connected: connected, strava_connect_url: '/en/virtual-ride/strava/connect/'}};
            eval(words + note);
            window.t = t;
            renderStravaNote();
        }""",
        {"words": _language_block(source), "note": note, "connected": connected},
    )
    if connected:
        # the connection shows: its rides go there, and the profile is where to manage it
        expect(page.locator("#stravaNote")).to_contain_text(page.evaluate("t('strava.on')"))
        manage = page.locator("#stravaNote a")
        expect(manage).to_have_text(page.evaluate("t('strava.manage')"))
        expect(manage).to_have_attribute("href", "/kk/accounts/profile/#virtual-rides-strava")
        return
    expect(page.locator("#stravaNote")).to_contain_text(page.evaluate("t('strava.offer')"))
    # Strava's own button, in the page's language, and back to the very page the member came from
    link = page.locator("#stravaNote a")
    expect(link).to_have_text("Connect with Strava")
    expect(link).to_have_attribute("href", "/ru/virtual-ride/strava/connect/?next=%2Fru%2Fvirtual-ride%2F%3Fgroup%3D5")


def test_the_track_puts_the_rider_back_on_the_map_where_the_route_is(page: Page):
    source = _trainer_source()
    code = "\n".join(
        _cut(source, pattern)
        for pattern in (
            r"^const ORIGIN = .*?;$",
            r"^function unproj\(x, z\) \{.*?\}$",
            r"^function proj\(lat, lon\) \{.*?\}$",
        )
    )
    back = page.evaluate(
        "code => { eval(code); const q = proj(43.2402, 76.929); const p = unproj(q.x, q.z); return [p.lat, p.lon]; }",
        code,
    )
    assert back == pytest.approx([43.2402, 76.929], abs=1e-9)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("connected", [False, True])
def test_the_profile_s_strava_controls_are_big_enough_to_tap(page: Page, live_server, settings, connected: bool):
    from trainer.models import StravaConnection

    settings.SOCIALACCOUNT_PROVIDERS = {
        **settings.SOCIALACCOUNT_PROVIDERS,
        "strava": {**settings.SOCIALACCOUNT_PROVIDERS["strava"], "APP": {"client_id": "1", "secret": "s"}},
    }
    member = User.objects.create_user(
        username="e2e_strava", email="e2e_strava@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    if connected:
        StravaConnection.objects.create(
            user=member, athlete_id=1, access_token="a", refresh_token="r", expires_at="2099-01-01T00:00:00Z"
        )
    inject_session(page, live_server, member)
    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/kk/accounts/profile/")
    control = page.locator("#virtual-rides-strava button" if connected else "#virtual-rides-strava a")
    control.scroll_into_view_if_needed()
    wide, high = control.evaluate(_REACH)
    assert wide >= 44 and high >= 44, (wide, high)


def test_a_ride_strava_keeps_processing_is_said_to_be_there_later(page: Page):
    source = _trainer_source()
    show = _cut(source, r"^let stravaFor = null;.*?^function stravaShow\(rideId, s, tries = 0\) \{.*?^\}")
    page.set_content('<p id="resStrava" class="hidden"></p>')
    page.evaluate(
        """({words, show}) => {
            const $ = s => document.querySelector(s);
            const Site = {get: async () => ({status: 'processing'})};
            const setTimeout = later => Promise.resolve().then(later); // half a minute of asking, at once
            eval(words + show + '; window.stravaShow = stravaShow; window.t = t;');
            stravaShow(5, {status: 'processing'});
        }""",
        {"words": _language_block(source), "show": show},
    )
    expect(page.locator("#resStrava")).to_have_text(page.evaluate("t('strava.later')"))


def test_every_button_of_the_setup_page_is_big_enough_to_tap_on_a_phone(page: Page, live_server):
    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=kk")
    # the words are in place before the 3D starts, and the buttons with them: a browser that cannot
    # draw 3D (a headless Firefox on CI) has them too
    expect(page.locator("#btnStart")).to_have_text(page.evaluate("TEXT.kk.start"))
    small = page.evaluate(
        """() => [...document.querySelectorAll('#menu .btn')].filter(b => b.offsetParent)
            .map(b => [b.id || b.textContent.trim(), b.getBoundingClientRect().height]).filter(([, h]) => h < 44)"""
    )
    assert small == [], small


def test_a_device_without_3d_is_told_so_and_the_page_raises_nothing_more(page: Page, live_server):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # a browser that cannot draw 3D, as a headless Firefox on CI cannot
    page.add_init_script(
        """(() => { const get = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
                return /webgl/.test(kind) ? null : get.call(this, kind, ...rest); }; })()"""
    )
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    expect(page.locator("#loading")).to_contain_text(page.evaluate("TEXT.en['boot.failed'].split('{')[0]"))
    page.wait_for_timeout(1500)  # the fonts arrive after the failed start
    assert errors == [], errors


_A_MEMBER_ASKS = {
    "GET /api/v1/virtual-ride/me",
    "GET /api/v1/virtual-ride/records",
    "GET /api/v1/virtual-ride/rides?limit=30",
    "POST /api/v1/virtual-ride/presence",
}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("member", [False, True])
def test_the_trainer_asks_the_site_only_what_a_ride_needs(page: Page, live_server, member: bool):
    if member:
        rider = User.objects.create_user(
            username="e2e_vr_asks", email="e2e_vr_asks@test.local", password="testpass123!", role=User.Role.PARTICIPANT
        )
        inject_session(page, live_server, rider)
    asked, sent = [], []

    def note(request):
        if "alatau" in request.frame.url and request.url.startswith(live_server.url) and "/static/" not in request.url:
            asked.append(f"{request.method} {request.url.removeprefix(live_server.url)}")
            if request.post_data:
                sent.append(json.loads(request.post_data))

    page.on("request", note)
    page.goto(f"{live_server.url}/en/virtual-ride/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)  # the lobby reports itself once settled
    # the ride itself runs in the browser: a guest is only asked who they are, a member also gets their
    # records and tells the lobby where they are -- in the fields the site takes, nothing more
    assert set(asked) <= (_A_MEMBER_ASKS if member else {"GET /api/v1/virtual-ride/me"}), asked
    assert all(set(body) <= set(PresenceIn.model_fields) for body in sent), sent
    ready = page.frame_locator("iframe.virtual-ride-frame").locator("html").evaluate("() => phase === 'menu'")
    if ready:  # a browser that draws 3D reaches the menu, and asks; one that cannot stops before asking
        assert "GET /api/v1/virtual-ride/me" in asked, asked


_RIDE_ALONE = ("text/ru.js", "text/kk.js", "text/en.js", "js/page.js", "js/track.js", "js/physics.js", "js/ride.js")


def _ride_alone(page: Page) -> list[str]:
    """The ride's own files in an empty page -- no scene, no HUD, no devices -- and a rider at a flat road's start."""
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_content("<!doctype html><title>ride</title>")
    for name in _RIDE_ALONE:
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    page.evaluate(
        """() => {
            const L = 20000, T = { N: 2, X: [0, 0], Y: [800, 800], Z: [0, -L], D: [0, L], L, loop: false };
            world = { T, S0: 20, FIN: L - 8, route: { id: 'flat' }, lms: [] };
            me = startRider(newRider('me', 0, 75, world.S0, 2)); Object.assign(me, { bike: 8, CdA: .3, Crr: .004 });
            phase = 'race';
        }"""
    )
    return errors


def test_the_ride_rides_without_the_page_the_scene_or_the_devices(page: Page):
    errors = _ride_alone(page)
    ridden = page.evaluate(
        """() => {
            const inp = { P: 200, cad: 85, mode: 'power', hr: 140, direct: false };
            for (let i = 1; i <= 3600; i++) stepRide(1 / 60, inp, i / 60);
            const st = me.stats;
            return { m: me.s - world.S0, t: st.t, points: me.track.length, beats: st.nHR, real: st.real };
        }"""
    )
    # a minute at 200 W: carried along the road, the track kept a point a second, the power meter counted as real
    assert ridden["m"] > 400 and ridden["t"] == pytest.approx(60) and ridden["points"] >= 59, ridden
    assert ridden["beats"] == 3600 and ridden["real"], ridden
    assert errors == [], errors


def test_a_rider_settles_where_the_power_meets_the_drag(page: Page):
    _ride_alone(page)
    v, rho, g = page.evaluate(
        """() => {
            const inp = { P: 200, cad: 85, mode: 'power', direct: false };
            for (let i = 1; i <= 240 * 60; i++) stepRide(1 / 60, inp, i / 60);
            return [me.v, PHYS.rho, PHYS.g];
        }"""
    )
    # on the flat 200 W = v * (air rho * CdA * v^2 / 2 + rolling Crr * m * g): CdA .3, Crr .004, 75 + 8 kg
    lo, hi = 0.0, 30.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mid * (rho * 0.3 * mid * mid / 2 + 0.004 * 83 * g) < 200 else (lo, mid)
    assert v == pytest.approx(lo, abs=0.01)


def test_a_smart_trainer_is_set_to_the_riders_own_drag(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    sent, rho = page.evaluate(
        """() => {
            globalThis.settings = { difficulty: 50 };
            const trainer = new BLEDev({ name: 'trainer' }), sent = [];
            trainer.ctrl = true; trainer.roles.add('trainer'); trainer.write = async bytes => { sent.push(bytes); };
            Sensors.devs.push(trainer);
            Object.assign(me, { CdA: .35, Crr: .0058 });
            Trainer.update(10, 6, me);
            return [sent, PHYS.rho];
        }"""
    )
    # 6 % at half the difficulty is 3 % (300 in 0.01 %); then the rider's own rolling resistance (in 0.0001)
    # and wind resistance CdA x air density (in 0.01 kg/m), not a trainer's defaults
    assert sent == [[0x11, 0, 0, 300 & 255, 300 >> 8, 58, round(0.35 * rho * 100)]], sent
    assert errors == [], errors


def test_the_ride_keeps_real_time_on_a_device_that_draws_a_few_frames_a_second(page: Page):
    _ride_alone(page)
    ridden = page.evaluate(
        """() => {
            const inp = { P: 200, cad: 85, mode: 'power', direct: false }, ride = fps => {
                me = startRider(newRider('me', 0, 75, world.S0, 2)); Object.assign(me, { bike: 8, CdA: .3, Crr: .004 });
                raceT = 0;
                for (let i = 1; i <= 120 * fps; i++) advanceRide(1 / fps, inp, i / fps);
                return [me.s - world.S0, raceT];
            };
            return [ride(60), ride(4)];
        }"""
    )
    # two minutes at 200 W, drawn 60 times a second and 4: two minutes ridden either way, and the same road
    (fast, fast_time), (slow, slow_time) = ridden
    assert fast_time == pytest.approx(120) and slow_time == pytest.approx(120), ridden
    assert slow == pytest.approx(fast, rel=0.005), ridden


# The page's clock and frames in the test's hands: drawFrame(ms) draws one frame ms later.
_FRAMES = """(() => {
    let now = 1000; const frames = [];
    performance.now = () => now;
    window.requestAnimationFrame = callback => frames.push(callback);
    window.drawFrame = ms => { now += ms; frames.splice(0).forEach(callback => callback(now)); };
    window.takeTime = ms => { now += ms; };
})()"""


def _trainer_in_its_menu(page: Page, live_server) -> None:
    page.add_init_script(_FRAMES)
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.evaluate("drawFrame(16)")
    if not page.evaluate("typeof phase !== 'undefined' && phase === 'menu'"):
        pytest.skip("this browser cannot draw 3D, so no ride starts in it")


@pytest.mark.django_db(transaction=True)
def test_the_countdown_does_not_count_the_time_the_course_took_to_build(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        "() => { const build = buildWorld; buildWorld = route => { build(route); takeTime(2000); }; startRace(); }"
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(16)")
    # a slow phone takes two seconds to build the course: none of them comes off the countdown, which a
    # group race starts at the server's time
    assert page.evaluate("cdT") > 3.9


@pytest.mark.django_db(transaction=True)
def test_the_heart_rate_reads_on_one_line_like_the_cadence(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate("() => { Sensors.hr = () => 142; settings.mode = 'free'; startRace(); }")
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")  # the HUD is drawn every tenth of a second
    beats, unit = (page.locator(s).bounding_box() for s in ("#vHR", "#uHR"))
    assert beats and unit
    # the unit beside the figure, not under it
    assert unit["x"] >= beats["x"] + beats["width"] and unit["y"] < beats["y"] + beats["height"], (beats, unit)
    # the figure in the HUD's own ink, readable over a light sky; the zone's colour is the heart's
    ink, figure, heart = page.evaluate(
        """() => [getComputedStyle(document.querySelector('#hudTop')).color,
            getComputedStyle(document.querySelector('#vHR')).color,
            getComputedStyle(document.querySelector('#vHR'), '::before').color]"""
    )
    assert figure == ink and heart != ink, (ink, figure, heart)


@pytest.mark.django_db(transaction=True)
def test_a_cadence_plan_shows_its_first_step_during_the_countdown(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate("() => { settings.mode = 'plan'; startRace(); }")
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")
    first = page.evaluate("settings.plan.steps[0].cad")
    expect(page.locator("#tVal")).to_have_text(str(first))
    expect(page.locator("#plItems li.cur")).to_have_count(1)


# The HUD's blocks: none may cover another.
_OVERLAPS = """() => {
    const boxes = ['#planList', '#hudTop .tbar', '#hudTop .prow', '#hudTR .mapcard']
        .map(s => [s, document.querySelector(s).getBoundingClientRect()]);
    const hits = [];
    for (const [i, [a, p]] of boxes.entries()) for (const [b, q] of boxes.slice(i + 1)) {
        const wide = Math.min(p.right, q.right) - Math.max(p.left, q.left);
        const high = Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top);
        if (wide > 1 && high > 1) hits.push(a + ' / ' + b);
    }
    return hits;
}"""


@pytest.mark.parametrize("size", [(1024, 768), (900, 600), (768, 1024)])
@pytest.mark.django_db(transaction=True)
def test_on_a_tablet_the_hud_s_blocks_keep_apart_in_a_cadence_plan(page: Page, live_server, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    _trainer_in_its_menu(page, live_server)
    page.evaluate("() => { settings.mode = 'plan'; startRace(); }")
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")
    assert page.evaluate(_OVERLAPS) == []


@pytest.mark.django_db(transaction=True)
def test_the_hud_does_not_animate_for_a_reader_who_asked_for_less_motion(page: Page, live_server):
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    durations = page.evaluate(
        "['#grade', '#vProg'].map(s => getComputedStyle(document.querySelector(s)).transitionDuration)"
    )
    assert durations == ["0s", "0s"]


@pytest.mark.django_db(transaction=True)
def test_a_cadence_plan_s_time_to_the_end_is_not_cut_off_on_a_phone_held_sideways(page: Page, live_server):
    page.set_viewport_size({"width": 844, "height": 390})
    page.add_init_script(_FRAMES)
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=kk")  # the longest words
    page.evaluate("drawFrame(16)")
    if not page.evaluate("typeof phase !== 'undefined' && phase === 'menu'"):
        pytest.skip("this browser cannot draw 3D, so no ride starts in it")
    page.evaluate("() => { settings.mode = 'plan'; startRace(); }")
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")
    left, edge = page.evaluate(
        "() => ['#plLeft', '#planList'].map(s => document.querySelector(s).getBoundingClientRect().right)"
    )
    assert left <= edge, (left, edge)


def _luminance(rgb: str) -> float:
    def linear(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(int(v)) for v in re.findall(r"\d+", rgb)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.mark.parametrize("state", ["act-ok", "act-near", "act-off"])
@pytest.mark.django_db(transaction=True)
def test_the_cadence_against_the_target_reads_over_a_light_sky(page: Page, live_server, state):
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    colour, weight, size = page.evaluate(
        """state => { const cad = document.querySelector('#vCad'); cad.className = state;
            const c = getComputedStyle(cad); return [c.color, c.fontWeight, parseFloat(c.fontSize)]; }""",
        state,
    )
    # the HUD's panel, rgba(11,17,24,.58), over a light sky (170,205,235)
    panel = "rgb(78, 96, 113)"
    lighter, darker = sorted((_luminance(colour), _luminance(panel)), reverse=True)
    # bold from 18.66 px is large text, which WCAG asks 3:1 of
    assert int(weight) >= 700 and size >= 18.66, (weight, size)
    assert (lighter + 0.05) / (darker + 0.05) >= 3, colour
