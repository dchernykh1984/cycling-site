"""Record labels render independently of WebGL and external trainer sensors."""

import json
import math
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


@pytest.mark.parametrize("connected, send", [(False, False), (True, True), (True, False)])
def test_the_setup_page_offers_strava_or_says_the_rides_go_there(page: Page, connected: bool, send: bool):
    source = _trainer_source()
    note = _cut(source, r"^function renderStravaNote\(\) \{.*?^\}")
    page.set_content('<style>.hidden{display:none}</style><p id="stravaNote" class="hidden"></p>')
    page.evaluate(
        """({words, note, connected, send}) => {
            const $ = s => document.querySelector(s);
            const STRAVA_LOGO = '', topPath = () => '/ru/virtual-ride/?group=5';
            const Records = {accountUrl: '/kk/accounts/profile/', me: {authenticated: true, strava_available: true,
                strava_connected: connected, strava_send: send,
                strava_connect_url: '/en/virtual-ride/strava/connect/'}};
            eval(words + note);
            window.t = t;
            renderStravaNote();
        }""",
        {"words": _language_block(source), "note": note, "connected": connected, "send": send},
    )
    if connected:
        # the connection shows, with whether its box sends the rides there (issue #471), and the profile is
        # where to manage it
        expect(page.locator("#stravaNote")).to_contain_text(
            page.evaluate("send => send ? t('strava.on') : t('strava.off')", send)
        )
        manage = page.locator("#stravaNote a")
        expect(manage).to_have_text(page.evaluate("t('strava.manage')"))
        expect(manage).to_have_attribute("href", "/kk/accounts/profile/#virtual-rides-strava")
        return
    expect(page.locator("#stravaNote")).to_contain_text(page.evaluate("t('strava.offer')"))
    # Strava's own button, in the page's language, and back to the very page the member came from
    link = page.locator("#stravaNote a")
    expect(link).to_have_text("Connect with Strava")
    expect(link).to_have_attribute("href", "/ru/virtual-ride/strava/connect/?next=%2Fru%2Fvirtual-ride%2F%3Fgroup%3D5")


@pytest.mark.parametrize("connected, send", [(False, False), (True, True), (True, False)])
def test_the_setup_page_offers_intervals_icu_or_says_where_the_rides_go(page: Page, connected: bool, send: bool):
    """Issue #471: the note says whether rides go to intervals.icu; the profile is where to connect or manage it."""
    source = _trainer_source()
    note = _cut(source, r"^function renderIntervalsNote\(\) \{.*?^\}")
    page.set_content('<style>.hidden{display:none}</style><p id="intervalsNote" class="hidden"></p>')
    page.evaluate(
        """({words, note, connected, send}) => {
            const $ = s => document.querySelector(s);
            const Records = {accountUrl: '/kk/accounts/profile/', me: {authenticated: true, intervals_available: true,
                intervals_connected: connected, intervals_send: send}};
            eval(words + note);
            window.t = t;
            renderIntervalsNote();
        }""",
        {"words": _language_block(source), "note": note, "connected": connected, "send": send},
    )
    said = "send ? t('intervals.on') : t('intervals.off')" if connected else "t('intervals.offer')"
    expect(page.locator("#intervalsNote")).to_contain_text(page.evaluate(f"send => {said}", send))
    link = page.locator("#intervalsNote a")
    expect(link).to_have_text(page.evaluate("t('intervals.manage')" if connected else "t('intervals.connect')"))
    expect(link).to_have_attribute("href", "/kk/accounts/profile/#virtual-rides-intervals")


def test_the_track_puts_the_rider_back_on_the_map_where_the_route_is(page: Page):
    source = _trainer_source()
    code = "\n".join(
        _cut(source, pattern)
        for pattern in (r"^function unproj\(x, z, O\) \{.*?\}$", r"^function proj\(lat, lon, O\) \{.*?\}$")
    )
    back = page.evaluate(
        """code => {
            eval(code); const O = { lat: 43.238, lon: 76.945 };
            const q = proj(43.2402, 76.929, O), p = unproj(q.x, q.z, O); return [p.lat, p.lon];
        }""",
        code,
    )
    assert back == pytest.approx([43.2402, 76.929], abs=1e-9)


# The files a map is laid out with, apart from the scene and the page
_MAP_ALONE = ("text/ru.js", "text/kk.js", "text/en.js", "js/page.js", "js/i18n.js", "js/maps.js", "js/track.js")


def test_a_map_far_from_the_others_is_laid_out_from_its_own_origin(page: Page):
    """A kilometre's road east to west, a thousand kilometres north of the first map, is a kilometre on the scene:
    laid out from the first map's origin it would come out 16 % longer, its latitude's degrees being shorter."""
    page.set_content("<!doctype html><title>map</title>")
    page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js")
    for name in _MAP_ALONE:
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    laid = page.evaluate(
        """() => {
            const named = { ru: 'n', kk: 'n', en: 'n' };
            const east = { id: 'east', name: named, desc: named, loop: false, width: 9, lanes: 2, scenery: 'city',
                           pts: [[51.17, 71.43, 350], [51.17, 71.4443, 350]] };
            addMap({ id: 'north', name: named, origin: { lat: 51.16, lon: 71.43 }, routes: [east] });
            const T = buildTrack(ROUTES.find(r => r.id === 'east')), end = unproj(T.X[T.N - 1], T.Z[T.N - 1], T.origin);
            return { length: T.L, end: [end.lat, end.lon] };
        }"""
    )
    lat, (lon1, lon2) = math.radians(51.17), (math.radians(71.43), math.radians(71.4443))
    metres = 2 * 6371000 * math.asin(math.cos(lat) * math.sin((lon2 - lon1) / 2))  # the great circle between the ends
    assert laid["length"] == pytest.approx(metres, rel=0.002), laid
    assert laid["end"] == pytest.approx([51.17, 71.4443], abs=1e-6), laid


def test_a_route_passes_the_sights_of_its_own_map_only(page: Page):
    """Two maps may list one sight, each for its own routes: on either route it stands once, not twice."""
    page.set_content("<!doctype html><title>map</title>")
    page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js")
    for name in _MAP_ALONE:
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    passed = page.evaluate(
        """() => {
            const named = n => ({ ru: n, kk: n, en: n }), origin = { lat: 51.16, lon: 71.43 };
            const road = id => ({ id, name: named(id), desc: named('-'), loop: false, width: 9, lanes: 2,
                                  scenery: 'city', pts: [[51.17, 71.43, 350], [51.17, 71.4443, 350]] });
            const tower = { type: 'glass', name: named('Tower'), lat: 51.1705, lon: 71.437, h: 90, r: 30 };
            addMap({ id: 'one', name: named('One'), origin, routes: [road('a')], landmarks: [tower] });
            addMap({ id: 'two', name: named('Two'), origin, routes: [road('b')], landmarks: [tower] });
            const by = id => nearLandmarks(buildTrack(ROUTES.find(r => r.id === id))).map(l => l.name);
            return { a: by('a'), b: by('b') };
        }"""
    )
    assert passed == {"a": ["Tower"], "b": ["Tower"]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("connected", [False, True])
def test_the_profile_s_service_controls_are_big_enough_to_tap(page: Page, live_server, settings, connected: bool):
    """Strava and intervals.icu (issue #471): every control answers a tap across 44 px, each button its own name."""
    from trainer import secret_box
    from trainer.models import IntervalsConnection, StravaConnection

    settings.SOCIALACCOUNT_PROVIDERS = {
        **settings.SOCIALACCOUNT_PROVIDERS,
        "strava": {**settings.SOCIALACCOUNT_PROVIDERS["strava"], "APP": {"client_id": "1", "secret": "s"}},
    }
    member = User.objects.create_user(
        username="e2e_strava", email="e2e_strava@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    if connected:
        StravaConnection.objects.create(
            user=member,
            athlete_id=1,
            access_token=secret_box.seal("a"),
            refresh_token=secret_box.seal("r"),
            expires_at="2099-01-01T00:00:00Z",
        )
        IntervalsConnection.objects.create(user=member, athlete_id="i1", api_key=secret_box.seal("k"))
    inject_session(page, live_server, member)
    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/kk/accounts/profile/")
    controls = page.locator(
        "#virtual-rides-services button, #virtual-rides-services a, #virtual-rides-services .form-check, "
        "#virtual-rides-services .form-control"
    )
    assert controls.count() == (6 if connected else 4)
    for i in range(controls.count()):
        control = controls.nth(i)
        control.scroll_into_view_if_needed()
        wide, high = control.evaluate(_REACH)
        assert wide >= 44 and high >= 44, (i, wide, high)
    # two buttons that act on different services never share a name (the interface's rule 12)
    names = [name.strip() for name in page.locator("#virtual-rides-services button").all_inner_texts()]
    assert len(names) == len(set(names)), names
    # and on the narrowest phone, in the longest words, the block scrolls nothing sideways
    page.set_viewport_size({"width": 320, "height": 740})
    wide = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert wide[0] <= wide[1], wide


@pytest.mark.parametrize("width", [360, 320])
def test_a_recent_ride_on_both_services_fits_a_phone(page: Page, live_server, width: int):
    """Issue #471: a ride linked on Strava and on intervals.icu, in the longest words, scrolls nothing sideways."""
    from trainer.models import IntervalsUpload, StravaUpload, VirtualRide

    member = User.objects.create_user(
        username="e2e_both", email="e2e_both@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    ride = VirtualRide.objects.create(
        user=member, route="center", route_name="Center loop", duration_s=3725, distance_m=31400
    )
    StravaUpload.objects.create(ride=ride, status=StravaUpload.Status.DONE, activity_id="12345678901")
    IntervalsUpload.objects.create(ride=ride, status=IntervalsUpload.Status.DONE, activity_id="i98765432")
    inject_session(page, live_server, member)
    page.set_viewport_size({"width": width, "height": 740})
    page.goto(f"{live_server.url}/kk/accounts/profile/")
    expect(page.locator('a[href="https://intervals.icu/activities/i98765432"]')).to_be_visible()
    wide = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert wide[0] <= wide[1], wide


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


def test_a_ride_s_intervals_icu_result_links_it_or_offers_another_try(page: Page):
    """Issue #471: the results say the ride is on intervals.icu with a link, or why not with "Send again"."""
    source = _trainer_source()
    show = _cut(source, r"^let intervalsFor = null;.*?^function intervalsShow\(rideId, s\) \{.*?^\}")
    page.set_content('<p id="resIntervals" class="hidden"></p>')
    page.evaluate(
        """({words, show}) => {
            const $ = s => document.querySelector(s);
            window.sent = [];
            const done = {status: 'done', activity_url: 'https://intervals.icu/activities/i9'};
            // intervals.icu answers when the test says so: the try is still on its way until then
            const answered = new Promise(resolve => { window.answer = () => resolve(done); });
            const Site = {post: path => { window.sent.push(path); return answered; }};
            eval(words + show + '; window.intervalsShow = intervalsShow; window.t = t;');
            intervalsShow(5, {status: 'failed', error: 'slow'});
        }""",
        {"words": _language_block(source), "show": show},
    )
    result = page.locator("#resIntervals")
    expect(result).to_contain_text(page.evaluate("t('intervals.failed', {msg: 'slow'})"))
    again = result.locator("button")
    again.click()
    # a second tap while the first try is on its way sends nothing more
    expect(again).to_be_disabled()
    again.click(force=True)
    page.evaluate("window.answer()")
    expect(result.locator("a")).to_have_attribute("href", "https://intervals.icu/activities/i9")
    assert page.evaluate("window.sent") == ["/rides/5/intervals"]


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
    "GET /api/v1/virtual-ride/settings",
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
    # records and settings and tells the lobby where they are -- in the fields the site takes, nothing more
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
            const L = 20000, origin = { lat: 0, lon: 0 };
            const T = { N: 2, X: [0, 0], Y: [800, 800], Z: [0, -L], D: [0, L], L, loop: false, origin };
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
            return [me.v, me.rho, PHYS.g];
        }"""
    )
    # on the flat 200 W = v * (air rho * CdA * v^2 / 2 + rolling Crr * m * g): CdA .3, Crr .004, 75 + 8 kg
    assert v == pytest.approx(_settled(rho, 0.3, g), abs=0.01)


def _settled(rho: float, cda: float, g: float) -> float:
    """The speed at which 200 W meets the drag on the flat: rider and bike of 83 kg, Crr .004."""
    lo, hi = 0.0, 30.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mid * (rho * cda * mid * mid / 2 + 0.004 * 83 * g) < 200 else (lo, mid)
    return lo


_STILL = "{ P: 0, cad: 0, mode: 'power', direct: false }"


def test_the_air_thins_with_the_height_as_the_standard_atmosphere_has_it(page: Page):
    errors = _ride_alone(page)
    air = page.evaluate(
        f"""() => [0, 1000, 2000, 3000].map(h => {{
            world.T.Y = [h, h]; stepRide(1 / 60, {_STILL}, 0); return me.rho;
        }})"""
    )
    # the table of the International Standard Atmosphere (ISO 2533), kg/m3
    assert air == pytest.approx([1.2250, 1.1117, 1.0066, 0.9093], abs=5e-4)
    assert errors == [], errors


def test_a_rider_close_behind_another_rides_in_its_wake(page: Page):
    """As the on-site measurements have it (Spoelstra et al. 2020): 45 % of the drag saved in line 0.7 m behind the
    wheel, 1.3 points more for each 10 cm closer, 3.9 less for each 10 cm aside; nothing alongside, far behind,
    well aside, or for the one in front."""
    errors = _ride_alone(page)
    shares = page.evaluate(
        f"""() => {{
            globalThis.mpStepRemote = () => {{}};
            const other = newRider('other', 0, 75, 0, 2); other.remote = true; bots = [other];
            // the bikes are 1.71 m long: their points 1.71 m apart leave no gap between the wheels
            const share = (gap, side) => {{
                other.s = me.s + 1.71 + gap; other.lane = me.lane + side;
                stepRide(1 / 60, {_STILL}, 0); return me.draft;
            }};
            return [share(.7, 0), share(.3, 0), share(.7, .1), share(-.5, 0),
                    share(4.5, 0), share(.7, 1.3), share(-4, 0)];
        }}"""
    )
    assert shares == pytest.approx([0.45, 0.502, 0.411, 0, 0, 0, 0], abs=1e-3)
    assert errors == [], errors


def test_in_a_wake_the_same_power_rides_faster(page: Page):
    errors = _ride_alone(page)
    v, rho, g = page.evaluate(
        """() => {
            // a live rider who keeps 0.7 m ahead of the wheel, in line: 45 % of the air drag saved
            globalThis.mpStepRemote = b => { b.s = me.s + 1.71 + .7; };
            const ahead = newRider('ahead', 0, 75, me.s + 2.41, me.lane); ahead.remote = true; bots = [ahead];
            const inp = { P: 200, cad: 85, mode: 'power', direct: false };
            for (let i = 1; i <= 240 * 60; i++) stepRide(1 / 60, inp, i / 60);
            return [me.v, me.rho, PHYS.g];
        }"""
    )
    assert v == pytest.approx(_settled(rho, 0.3 * 0.55, g), abs=0.01)
    assert v > _settled(rho, 0.3, g) + 1
    assert errors == [], errors


def test_a_bot_behind_the_rider_rides_in_the_riders_wake(page: Page):
    errors = _ride_alone(page)
    share = page.evaluate(
        f"""() => {{
            const bot = newRider('bot', 0, 70, me.s - 1.71 - .7, me.lane);
            Object.assign(bot, {{ ch: {{ style: 'rouleur' }}, wkg: 3, seed: 1 }}); bots = [bot];
            stepRide(1 / 60, {_STILL}, 0); return bot.draft;
        }}"""
    )
    assert share == pytest.approx(0.45, abs=1e-3)
    assert errors == [], errors


def _trainer_answering(page: Page) -> None:
    """A smart trainer that takes every command, answered as FTMS answers; what it is sent is in `sent`."""
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    page.evaluate(
        """() => {
            globalThis.settings = { difficulty: 50 }; globalThis.sent = [];
            const trainer = new BLEDev({ name: 'trainer' });
            trainer.ctrl = true; trainer.roles.add('trainer');
            trainer.write = async bytes => {
                sent.push(bytes);
                setTimeout(() => trainer.onCtrl(new DataView(new Uint8Array([0x80, bytes[0], 1]).buffer)), 0);
            };
            Sensors.devs.push(trainer);
        }"""
    )


def test_a_smart_trainer_is_set_to_the_riders_own_drag(page: Page):
    errors = _ride_alone(page)
    _trainer_answering(page)
    sent, rho = page.evaluate(
        f"""() => {{
            stepRide(1 / 60, {_STILL}, 0);
            Object.assign(me, {{ CdA: .35, Crr: .0058 }});
            Trainer.update(10, 6, me);
            return [sent, me.rho];
        }}"""
    )
    # 6 % at half the difficulty is 3 % (300 in 0.01 %); then the rider's own rolling resistance (in 0.0001)
    # and wind resistance CdA x the air's density at their height (in 0.01 kg/m), not a trainer's defaults
    assert sent == [[0x11, 0, 0, 300 & 255, 300 >> 8, 58, round(0.35 * rho * 100)]], sent
    assert errors == [], errors


def test_a_smart_trainer_is_told_the_lighter_drag_of_a_wake_at_once(page: Page):
    errors = _ride_alone(page)
    _trainer_answering(page)
    sent, rho = page.evaluate(
        f"""async () => {{
            globalThis.mpStepRemote = () => {{}};
            const ahead = newRider('ahead', 0, 75, me.s + 1.71 + .7, me.lane); ahead.remote = true; bots = [ahead];
            Object.assign(me, {{ CdA: .35, Crr: .0058 }});
            const at = async t => {{
                stepRide(1 / 60, {_STILL}, 0); Trainer.update(t, 6, me);
                await new Promise(done => setTimeout(done, 50));
            }};
            await at(10);                    // in the wake
            ahead.s += 10; await at(11.5);   // left behind: told within the second, the grade the same
            await at(13);                    // nothing changed: nothing sent
            return [sent, me.rho];
        }}"""
    )
    wake, alone = round(0.35 * (1 - 0.45) * rho * 100), round(0.35 * rho * 100)
    assert sent == [[0x11, 0, 0, 300 & 255, 300 >> 8, 58, cw] for cw in (wake, alone)], sent
    assert errors == [], errors


def test_a_cadence_sensor_alone_rides_by_the_physics_unless_the_gears_speed_is_chosen(page: Page):
    """Races and free rides take the physics by default; a step of the own plan by gears keeps the gear's speed."""
    errors = _ride_alone(page)
    page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / "js" / "input.js")
    direct = page.evaluate(
        """() => {
            const none = () => null;
            globalThis.Sensors = { mode: () => 'cadence', crank: () => 90, power: none, wheel: none, hr: none };
            globalThis.gearTeeth = () => [50, 17]; globalThis.gearF = 2; globalThis.gearR = 6;
            const by = cadSpeed => {
                globalThis.settings = { circ: 2105, trainer: 'fluid', cadSpeed }; return readInput().direct;
            };
            const ride = [by(undefined), by('physics'), by('direct')];
            Work.start([{ f: 2, r: 6, cad: 90, min: 5 }], [], null); Work.update(.1, 90, 'cadence', 0);
            return { ride, plan: [by(undefined), by('physics'), by('direct')] };
        }"""
    )
    assert direct == {"ride": [False, False, True], "plan": [True, True, True]}, direct
    assert errors == [], errors


def test_a_smart_trainer_that_answers_each_command_is_given_the_grade(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    written = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // as FTMS asks: each control point command is answered by an indication a moment later, and a
            // command written before the last one is answered is refused (Procedure Already In Progress)
            const written = [], point = { listeners: [], busy: false,
                addEventListener(name, fn) { this.listeners.push(fn); },
                async startNotifications() {},
                async writeValueWithResponse(data) {
                    const bytes = Array.from(data);
                    if (this.busy) {
                        written.push(['refused', ...bytes]);
                        throw new Error('Procedure Already In Progress');
                    }
                    written.push(bytes); this.busy = true;
                    setTimeout(() => {
                        this.busy = false;
                        const value = new DataView(new Uint8Array([0x80, bytes[0], 1]).buffer);
                        this.listeners.forEach(fn => fn({ target: { value } }));
                    }, 50);
                } };
            const bikeData = { addEventListener() {}, async startNotifications() {} };
            const ftms = { async getCharacteristic(uuid) { return uuid === 0x2AD9 ? point : bikeData; } };
            const server = {
                async getPrimaryService(uuid) { if (uuid === 0x1826) return ftms; throw new Error('none'); }
            };
            const gatt = { async connect() { return server; } };
            const trainer = new BLEDev({ name: 'trainer', addEventListener() {}, gatt });
            Sensors.devs.push(trainer);
            await trainer.connect();
            Trainer.update(10, 4, me);
            await new Promise(done => setTimeout(done, 300));
            return { written, ctrl: trainer.ctrl, sent: Trainer.sent };
        }"""
    )
    # control is asked for, then the start, each after the last was answered; then the route's 4 % goes out
    assert [bytes[:5] for bytes in written["written"]] == [[0x00], [0x07], [0x11, 0, 0, 400 & 255, 400 >> 8]], written
    assert written["ctrl"] and written["sent"] == 4, written
    assert errors == [], errors


def test_a_smart_trainer_that_takes_back_control_is_asked_once_then_left_alone(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    asked = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // another app took the trainer: every command is answered "control not permitted" (5)
            const trainer = new BLEDev({ name: 'trainer' }), written = [];
            trainer.ctrl = true; trainer.roles.add('trainer');
            trainer.write = async bytes => {
                written.push(bytes[0]);
                setTimeout(() => trainer.onCtrl(new DataView(new Uint8Array([0x80, bytes[0], 5]).buffer)), 10);
            };
            Sensors.devs.push(trainer);
            for (let t = 10; t < 15; t++) {
                Trainer.update(t, 4, me);
                await new Promise(done => setTimeout(done, 100));
            }
            return { written, ctrl: trainer.ctrl, sent: Trainer.sent };
        }"""
    )
    # the grade, refused; control asked for once, refused; then nothing more is written to that trainer
    assert asked == {"written": [0x11, 0x00], "ctrl": False, "sent": None}, asked
    assert errors == [], errors


def test_a_smart_trainer_that_never_answers_is_driven_all_the_same(page: Page):
    page.clock.install()
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    page.evaluate(
        """() => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // a trainer that takes every command and never indicates an answer, as some do
            const written = [], point = { addEventListener() {}, async startNotifications() {},
                async writeValueWithResponse(data) { written.push(data[0]); } };
            const bikeData = { addEventListener() {}, async startNotifications() {} };
            const ftms = { async getCharacteristic(uuid) { return uuid === 0x2AD9 ? point : bikeData; } };
            const server = {
                async getPrimaryService(uuid) { if (uuid === 0x1826) return ftms; throw new Error('-'); }
            };
            const gatt = { async connect() { return server; } };
            const trainer = new BLEDev({ name: 'trainer', addEventListener() {}, gatt });
            Sensors.devs.push(trainer);
            globalThis.silent = { written, trainer };
            trainer.connect();
        }"""
    )
    wait = page.evaluate("() => CONTROL_ANSWER_MS")  # how long a command is given its answer
    page.clock.run_for(wait // 2)
    assert page.evaluate("() => silent.written") == [0x00], "the start went out before the request was answered"
    # each unanswered command is given its time, then the next goes out: the start, then the route's grade
    page.clock.run_for(wait // 2 + 100)
    page.clock.run_for(wait + 100)
    page.evaluate("() => Trainer.update(10, 4, me)")
    page.clock.run_for(wait + 100)
    state = page.evaluate("() => ({ written: silent.written, ctrl: silent.trainer.ctrl, sent: Trainer.sent })")
    assert state == {"written": [0x00, 0x07, 0x11], "ctrl": True, "sent": 4}, state
    assert errors == [], errors


def test_a_grade_sent_before_the_trainer_reconnected_is_not_counted_as_on_it(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    sent = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // the link drops while the trainer has not answered the grade; the device comes back and answers
            const point = { listeners: [], answers: false,
                addEventListener(name, fn) { this.listeners.push(fn); },
                async startNotifications() {},
                async writeValueWithResponse(data) {
                    if (!this.answers) return;
                    const value = new DataView(new Uint8Array([0x80, data[0], 1]).buffer);
                    setTimeout(() => this.listeners.forEach(fn => fn({ target: { value } })), 10);
                } };
            const bikeData = { addEventListener() {}, async startNotifications() {} };
            const ftms = { async getCharacteristic(uuid) { return uuid === 0x2AD9 ? point : bikeData; } };
            const server = {
                async getPrimaryService(uuid) { if (uuid === 0x1826) return ftms; throw new Error('-'); }
            };
            const gatt = { async connect() { return server; } };
            const trainer = new BLEDev({ name: 'trainer', addEventListener() {}, gatt });
            trainer.ctrl = true; trainer.cpt = point; trainer.roles.add('trainer');
            Sensors.devs.push(trainer);
            Trainer.update(10, 4, me);
            point.answers = true;
            await trainer.connect(); Trainer.sent = null; // as the reconnection does
            await new Promise(done => setTimeout(done, CONTROL_ANSWER_MS + 300));
            return Trainer.sent;
        }"""
    )
    # the trainer that came back has not been told the 4 %, so the ride will tell it
    assert sent is None, sent
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


def _trainer_in_its_menu(page: Page, live_server, lang: str = "en") -> None:
    page.add_init_script(_FRAMES)
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang={lang}")
    page.evaluate("drawFrame(16)")
    if not page.evaluate("typeof phase !== 'undefined' && phase === 'menu'"):
        pytest.skip("this browser cannot draw 3D, so no ride starts in it")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("stored", "chosen"),
    [({}, "physics"), ({"cadSpeed": "direct"}, "physics"), ({"cadSpeed": "direct", "cadPhysics": True}, "direct")],
)
def test_the_physics_becomes_the_cadence_default_once_and_a_choice_after_it_is_kept(
    page: Page, live_server, stored, chosen
):
    # the gear's speed was the default, so a rider's stored settings carry it whether they chose it or not
    page.add_init_script(f"localStorage.setItem('alatau:settings', {json.dumps(json.dumps(stored))})")
    _trainer_in_its_menu(page, live_server)
    assert page.evaluate("[settings.cadSpeed, $('#cadSpeed').value]") == [chosen, chosen]


@pytest.mark.django_db(transaction=True)
def test_only_a_map_with_mountains_raises_a_range_beyond_its_routes(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    ranges = page.evaluate(
        """() => {
            const named = { ru: 'n', kk: 'n', en: 'n' };
            const flat = { id: 'flat', name: named, desc: named, loop: false, width: 9, lanes: 2, scenery: 'city',
                           pts: [[51.17, 71.43, 350], [51.17, 71.4443, 350]] };
            addMap({ id: 'steppe', name: named, origin: { lat: 51.16, lon: 71.43 }, routes: [flat] });
            // the range is the scenery's plane 90 km wide (addMountains)
            const wide = o => o.geometry && o.geometry.parameters && o.geometry.parameters.width === 90000;
            const range = id => {
                buildWorld(ROUTES.find(r => r.id === id));
                let n = 0; scenery.traverse(o => { if (wide(o)) n++; }); return n;
            };
            return { almaty: range('center'), steppe: range('flat') };
        }"""
    )
    assert ranges == {"almaty": 1, "steppe": 0}


@pytest.mark.django_db(transaction=True)
def test_a_city_s_button_lists_its_routes_and_picks_the_first_of_them(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        """() => {
            const named = n => ({ ru: n, kk: n, en: n });
            const road = id => ({ id, name: named(id), desc: named('-'), loop: false, width: 9, lanes: 2,
                                  scenery: 'city', pts: [[51.17, 71.43, 350], [51.17, 71.4443, 350]] });
            const routes = [road('east'), road('west')];
            addMap({ id: 'steppe', name: named('Steppe'), origin: { lat: 51.16, lon: 71.43 }, routes });
            renderMenu();
        }"""
    )
    cities, routes = page.locator("#cities"), page.locator("#routes .route b")
    almaty, steppe = cities.get_by_role("button", name="Almaty"), cities.get_by_role("button", name="Steppe")
    expect(almaty).to_have_attribute("aria-pressed", "true")
    steppe.click()
    expect(steppe).to_have_attribute("aria-pressed", "true")
    expect(almaty).to_have_attribute("aria-pressed", "false")
    expect(routes).to_have_text(["east", "west"])
    assert page.evaluate("routeSel") == "east"
    almaty.click()
    expect(routes).to_have_text(["Central loop", "Climb to Medeu", "Old centre", "Al-Farabi sprint"])
    assert page.evaluate("routeSel") == "center"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [360, 320])
def test_a_city_s_button_is_big_enough_to_tap_on_a_phone(page: Page, live_server, width: int):
    """A slim pill, tapped across 44 px: its zone reaches past its frame, and the rows keep apart so two zones
    never meet (the interface rules, 9). Each city's is measured, the ones coming soon too."""
    page.set_viewport_size({"width": width, "height": 740})
    _trainer_in_its_menu(page, live_server)
    cities = page.locator("#cities .city")
    expect(cities).to_have_count(3)
    for city in cities.all():
        city.scroll_into_view_if_needed()
        wide, high = city.evaluate(_REACH)
        assert wide >= 44 and high >= 44, (city.text_content(), wide, high)


@pytest.mark.django_db(transaction=True)
def test_a_remembered_route_no_map_has_any_more_gives_way_to_the_first(page: Page, live_server):
    page.add_init_script("localStorage.setItem('alatau:route', JSON.stringify('gone'))")
    _trainer_in_its_menu(page, live_server)
    assert page.evaluate("routeSel") == "center"
    page.evaluate("startRace()")
    page.wait_for_function("phase === 'countdown'", polling=100)


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


def _bluetooth(reopens: bool, stored: dict | None = None) -> str:
    """A browser's Bluetooth with one heart rate monitor in reach; `reopens` gives it getDevices(), as Chrome
    has behind its permissions flag. What the chooser was asked is in `chooserAsked`."""
    preset = "".join(
        f"localStorage.setItem('alatau:{k}', {json.dumps(json.dumps(v))});" for k, v in (stored or {}).items()
    )
    return """(() => {
        const characteristic = { addEventListener() {}, startNotifications: async () => {} };
        const server = { getPrimaryService: async uuid => {
            if (uuid !== 0x180D) throw new Error('not here'); return { getCharacteristic: async () => characteristic };
        } };
        const hrm = { id: 'hr-1', name: 'HRM Pro', watched: false, forgotten: false, addEventListener() {},
            gatt: { connect: async () => server, disconnect() {} } };
        hrm.watchAdvertisements = async () => { hrm.watched = true; };
        hrm.forget = async () => { hrm.forgotten = true; };
        window.hrm = hrm; window.chooserAsked = [];
        const bluetooth = { requestDevice: async options => { chooserAsked.push(options); return hrm; } };
        if (REOPENS) bluetooth.getDevices = async () => [hrm];
        Object.defineProperty(navigator, 'bluetooth', { value: bluetooth, configurable: true });
        if (!sessionStorage.getItem('preset')) { sessionStorage.setItem('preset', '1'); PRESET }
    })()""".replace("REOPENS", "true" if reopens else "false").replace("PRESET", preset)


def _listed(page: Page) -> list[str]:
    return page.locator("#devList li").evaluate_all(
        "items => items.map(li => li.innerText.replace(/\\s+/g, ' ').trim())"
    )


@pytest.mark.django_db(transaction=True)
def test_a_connected_device_is_listed_again_when_the_page_opens_next_time(page: Page, live_server):
    page.add_init_script(_bluetooth(reopens=False))
    _trainer_in_its_menu(page, live_server)
    page.click("#btnConnect")
    expect(page.locator("#devList li")).to_have_count(1)
    assert json.loads(page.evaluate("localStorage.getItem('alatau:devices')")) == [{"id": "hr-1", "name": "HRM Pro"}]
    page.reload()
    page.evaluate("drawFrame(16)")
    assert _listed(page) == ["HRM Pro not connected Connect Forget"]
    expect(page.locator("#btAuto")).not_to_be_checked()


@pytest.mark.django_db(transaction=True)
def test_connect_opens_the_chooser_with_the_remembered_device_alone(page: Page, live_server):
    page.add_init_script(_bluetooth(reopens=False, stored={"devices": [{"id": "old-id", "name": "HRM Pro"}]}))
    _trainer_in_its_menu(page, live_server)
    page.locator("#devList li").get_by_role("button", name="Connect: HRM Pro", exact=True).click()
    expect(page.locator("#devList li small")).to_have_text("connected")
    assert page.evaluate("chooserAsked.map(o => o.filters)") == [[{"name": "HRM Pro"}]]
    # the browser gave it another id: one entry for it still, under the new id
    assert json.loads(page.evaluate("localStorage.getItem('alatau:devices')")) == [{"id": "hr-1", "name": "HRM Pro"}]


@pytest.mark.django_db(transaction=True)
def test_with_the_box_on_remembered_devices_connect_as_the_page_opens(page: Page, live_server):
    stored = {"devices": [{"id": "hr-1", "name": "HRM Pro"}], "btAuto": True}
    page.add_init_script(_bluetooth(reopens=True, stored=stored))
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#devList li small")).to_have_text("connected")
    expect(page.locator("#btAuto")).to_be_checked()
    assert page.evaluate("[chooserAsked.length, hrm.watched]") == [0, True]


@pytest.mark.django_db(transaction=True)
def test_where_the_browser_cannot_reopen_a_device_the_box_says_what_to_turn_on(page: Page, live_server):
    stored = {"devices": [{"id": "hr-1", "name": "HRM Pro"}], "btAuto": True}
    page.add_init_script(_bluetooth(reopens=False, stored=stored))
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#btHint")).to_contain_text("chrome://flags/#enable-web-bluetooth-new-permissions-backend")
    assert _listed(page) == ["HRM Pro not connected Connect Forget"]
    assert page.evaluate("chooserAsked.length") == 0


@pytest.mark.django_db(transaction=True)
def test_forget_drops_a_remembered_device_here_and_in_the_browser(page: Page, live_server):
    page.add_init_script(_bluetooth(reopens=True, stored={"devices": [{"id": "hr-1", "name": "HRM Pro"}]}))
    _trainer_in_its_menu(page, live_server)
    page.locator("#devList li").get_by_role("button", name="Forget: HRM Pro", exact=True).click()
    expect(page.locator("#devList li")).to_have_count(0)
    assert page.evaluate("localStorage.getItem('alatau:devices')") == "[]"
    page.wait_for_function("hrm.forgotten === true")


def _member_on_the_trainer(page: Page, live_server, stored: dict | None = None) -> User:
    """A member signed in, a page of the site having handed out its CSRF cookie -- one without the trainer in a
    frame, which would sync on its own; `stored` is what this browser kept before."""
    member = User.objects.create_user(
        username="e2e_settings", email="e2e_settings@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    if stored is not None:
        page.add_init_script(
            "if (!sessionStorage.getItem('preset')) { sessionStorage.setItem('preset', '1');"
            f" localStorage.setItem('alatau:settings', {json.dumps(json.dumps(stored))}); }}"
        )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/en/accounts/profile/")
    return member


def _kept(member: User) -> tuple[dict, int] | None:
    from trainer.models import TrainerSettings

    kept = TrainerSettings.objects.filter(user=member).first()
    return (kept.data, kept.saved_at) if kept else None


@pytest.mark.django_db(transaction=True)
def test_a_member_s_settings_come_from_their_account_and_go_back_to_it(page: Page, live_server):
    from trainer.models import TrainerSettings

    member = _member_on_the_trainer(page, live_server)
    TrainerSettings.objects.create(user=member, data={"height": 191, "mass": 82, "circ": 2146}, saved_at=1000)
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#height")).to_have_value("191")
    expect(page.locator("#circ")).to_have_value("2146")
    with page.expect_response(lambda r: r.url.endswith("/virtual-ride/settings") and r.request.method == "PUT"):
        page.fill("#mass", "77")
        page.dispatch_event("#mass", "change")
    kept = _kept(member)
    assert kept is not None, "nothing kept with the account"
    data, saved_at = kept
    assert (data["height"], data["mass"], data["circ"]) == (191, 77, 2146), data
    assert saved_at > 1000
    assert "synced" not in data and "unsent" not in data, "the browser's own marks stay with it"


@pytest.mark.django_db(transaction=True)
def test_a_fresh_browser_never_sends_its_defaults_over_the_account(page: Page, live_server):
    member = _member_on_the_trainer(page, live_server)
    sent = []
    page.on("request", lambda r: sent.append(r.method) if r.url.endswith("/virtual-ride/settings") else None)
    _trainer_in_its_menu(page, live_server)
    page.wait_for_timeout(2500)  # past the pause a change waits before it is sent
    assert sent == ["GET"], sent
    assert _kept(member) is None


@pytest.mark.django_db(transaction=True)
def test_settings_kept_in_this_browser_before_go_to_an_empty_account(page: Page, live_server):
    member = _member_on_the_trainer(page, live_server, stored={"height": 185, "mass": 70})
    with page.expect_response(lambda r: r.url.endswith("/virtual-ride/settings") and r.request.method == "PUT"):
        _trainer_in_its_menu(page, live_server)
    kept = _kept(member)
    assert kept is not None, "nothing kept with the account"
    assert (kept[0]["height"], kept[0]["mass"]) == (185, 70), kept


@pytest.mark.django_db(transaction=True)
def test_an_old_browser_s_settings_never_replace_the_account_s(page: Page, live_server):
    from trainer.models import TrainerSettings

    member = _member_on_the_trainer(page, live_server, stored={"height": 185, "mass": 70})
    TrainerSettings.objects.create(user=member, data={"height": 191, "mass": 82}, saved_at=1000)
    sent = []
    page.on("request", lambda r: sent.append(r.method) if r.url.endswith("/virtual-ride/settings") else None)
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#height")).to_have_value("191")
    page.wait_for_timeout(2500)  # past the pause a change waits before it is sent
    assert sent == ["GET"], sent
    assert _kept(member) == ({"height": 191, "mass": 82}, 1000)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("own_copy", [True, False])
def test_a_browser_another_member_used_never_sends_their_settings_into_this_one_s_account(
    page: Page, live_server, own_copy
):
    from trainer.models import TrainerSettings

    other = {"height": 185, "mass": 70, "owner": 987654, "synced": 5, "unsent": True}
    member = _member_on_the_trainer(page, live_server, stored=other)
    if own_copy:
        TrainerSettings.objects.create(user=member, data={"height": 191, "mass": 82}, saved_at=1000)
    sent = []
    page.on("request", lambda r: sent.append(r.method) if r.url.endswith("/virtual-ride/settings") else None)
    _trainer_in_its_menu(page, live_server)
    page.wait_for_timeout(2500)  # past the pause a change waits before it is sent
    assert sent == ["GET"], sent
    if own_copy:
        expect(page.locator("#height")).to_have_value("191")
        assert _kept(member) == ({"height": 191, "mass": 82}, 1000)
    else:
        assert _kept(member) is None


@pytest.mark.django_db(transaction=True)
def test_a_browser_without_bluetooth_for_sites_offers_no_auto_connect(page: Page, live_server):
    page.add_init_script("Object.defineProperty(navigator, 'bluetooth', { value: undefined, configurable: true })")
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#btAuto")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_a_device_s_long_name_never_pushes_the_setup_sideways_on_a_narrow_phone(page: Page, live_server):
    devices = [{"id": "a", "name": "Wahoo KICKR CORE 5D91XXXXLONG"}, {"id": "b", "name": ""}]
    page.add_init_script(f"localStorage.setItem('alatau:devices', {json.dumps(json.dumps(devices))})")
    page.set_viewport_size({"width": 320, "height": 700})
    _trainer_in_its_menu(page, live_server)
    wide, room = page.evaluate(
        "[document.querySelector('.setup').scrollWidth, document.querySelector('.setup').clientWidth]"
    )
    assert wide <= room, (wide, room)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_menu_s_longest_choice_never_pushes_the_setup_sideways_on_a_narrow_phone(page: Page, live_server, lang):
    page.set_viewport_size({"width": 320, "height": 700})
    _trainer_in_its_menu(page, live_server, lang)
    page.evaluate(
        "document.querySelectorAll('.setup select').forEach(menu => {"
        " const longest = [...menu.options].sort((a, b) => b.text.length - a.text.length)[0];"
        " if (longest) menu.value = longest.value; })"
    )
    wide, room = page.evaluate(
        "[document.querySelector('.setup').scrollWidth, document.querySelector('.setup').clientWidth]"
    )
    assert wide <= room, (wide, room)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_route_s_card_keeps_inside_its_section_on_a_narrow_phone(page: Page, live_server, lang):
    page.set_viewport_size({"width": 320, "height": 700})
    _trainer_in_its_menu(page, live_server, lang)
    wide, room = page.evaluate(
        "[document.querySelector('#routes').scrollWidth, document.querySelector('#routes').clientWidth]"
    )
    assert wide <= room, (wide, room)
