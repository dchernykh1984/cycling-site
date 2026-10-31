"""Record labels render independently of WebGL and external trainer sensors."""

import re

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
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
def test_the_setup_page_offers_strava_only_to_a_member_who_has_not_connected_it(page: Page, connected: bool):
    source = _trainer_source()
    note = _cut(source, r"^function renderStravaNote\(\) \{.*?^\}")
    page.set_content('<style>.hidden{display:none}</style><p id="stravaNote" class="hidden"></p>')
    page.evaluate(
        """({words, note, connected}) => {
            const $ = s => document.querySelector(s);
            const STRAVA_LOGO = '', topPath = () => '/ru/virtual-ride/?group=5';
            const Records = {me: {authenticated: true, strava_available: true,
                strava_connected: connected, strava_connect_url: '/en/virtual-ride/strava/connect/'}};
            eval(words + note);
            window.t = t;
            renderStravaNote();
        }""",
        {"words": _language_block(source), "note": note, "connected": connected},
    )
    if connected:
        # its rides already go there, and the profile is where to turn it off
        expect(page.locator("#stravaNote")).to_be_hidden()
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
