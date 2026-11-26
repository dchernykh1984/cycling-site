"""Record labels render independently of WebGL and external trainer sensors."""

import json
import math
import re

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from accounts.models import User
from api.endpoints.virtual_ride import PresenceIn
from calendar_app.models import Discipline, DisciplineCategory, EventType
from tests import trainer_page
from tests.e2e import contrast
from tests.e2e.conftest import inject_session
from tests.e2e.test_interface_rules import _REACH
from trainer.models import GroupRide


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
        '<p id="mpStatus"></p><div id="mpOnline"></div><div id="mpGroups"></div>'
        '<select id="mpDelay"><option value="60"></option></select><button id="mpCreate"></button>'
        '<button id="mpEvent"></button>'
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
            const groupWind = () => null; // a race in still air
            const mpClash = () => false, MP_HOUR = 3600e3, LOCALE = 'en-GB'; // starting within the hour
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


def test_a_race_far_ahead_names_its_day_and_wind_and_one_too_near_a_member_s_own_cannot_be_joined(page: Page):
    source = _trainer_source()
    pieces = [
        _cut(source, pattern)
        for pattern in (
            r"^const MP_HOUR = .*?;$",
            r"^const mpClash = .*?;$",
            r"^const groupWind = .*?;$",
            r"^const windFrom = .*?;$",
            r"^function renderMP\(\) \{.*?^\}",
        )
    ]
    page.set_content(
        '<p id="mpStatus"></p><div id="mpOnline"></div><div id="mpGroups"></div>'
        '<select id="mpDelay"><option value="60"></option></select><button id="mpCreate"></button>'
        '<button id="mpEvent"></button>'
    )
    page.evaluate(
        """({words, code}) => {
            const $ = s => document.querySelector(s);
            const host = {user_id: 1, name: 'Anna'}, me = {user_id: 2, name: 'Me'}, day = 864e5, hour = 3600e3;
            const at = ms => new Date(Date.now() + ms).toISOString();
            // mine in two days; one an hour and a half after it; one half an hour after it, in a west wind
            window.MP = {status: 'on', online: [], offset: 0, groups: [
                {id: 1, route: 'center', route_name: 'Center', host: me, members: [me], is_host: true, is_member: true,
                 start_at: at(2 * day)},
                {id: 2, route: 'center', route_name: 'Center', host, members: [host], is_host: false, is_member: false,
                 start_at: at(2 * day + 1.5 * hour)},
                {id: 3, route: 'center', route_name: 'Center', host, members: [host], is_host: false, is_member: false,
                 start_at: at(2 * day + .5 * hour), wind_ms: 6, wind_from_deg: 270}
            ]};
            const Records = {me: {user_id: 2}}, mpStartLocal = g => Date.parse(g.start_at), LINKED = null;
            const fmtTime = String, routeName = String, routeTitle = g => g.route_name, hexs = String, mpColor = String;
            const mpMyGroup = () => null, renderStartSum = () => {}, mpAction = () => {};
            eval(words + code);
            window.t = t;
            renderMP();
        }""",
        {"words": _language_block(source), "code": "\n".join(pieces)},
    )
    cards = page.locator("#mpGroups > div")
    expect(cards.nth(0).locator("small")).to_contain_text(page.evaluate("t('mp.startsOn', { when: '' })").strip())
    expect(cards.nth(2).locator("small")).to_contain_text(page.evaluate("t('mp.wind', { ms: 6, from: t('wind.w') })"))
    # a race an hour and a half from the member's own may be joined; one half an hour from it may not
    expect(cards.nth(1).locator("button.act")).to_be_enabled()
    expect(cards.nth(2).locator("button.act")).to_be_disabled()


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


@pytest.mark.django_db(transaction=True)
def test_every_route_runs_on_without_turning_back_or_knotting(page: Page, live_server):
    # a route's points come from a map's streets: a spur ridden out and back, or two points on top of each other,
    # would make the rider turn round or twitch where the street goes straight on
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildTrack === 'function'")
    faults = page.evaluate(
        """() => ROUTES.flatMap(r => {
          const T = buildTrack(r), O = mapOf(r).origin, out = [];
          if ([...T.X, ...T.Y, ...T.Z].some(v => !Number.isFinite(v))) out.push(r.id + ': not a number');
          for (let i = 2; i < T.N; i++) {
            const a = Math.atan2(T.Z[i - 1] - T.Z[i - 2], T.X[i - 1] - T.X[i - 2]);
            const b = Math.atan2(T.Z[i] - T.Z[i - 1], T.X[i] - T.X[i - 1]);
            const turn = Math.abs(((b - a + 3 * Math.PI) % (2 * Math.PI)) - Math.PI) * 180 / Math.PI;
            if (turn > 60) {
              out.push(r.id + ': turns ' + Math.round(turn) + ' degrees at ' + Math.round(T.D[i]) + ' m');
              break;
            }
          }
          for (let i = 1; i < r.pts.length; i++) {
            const p = proj(r.pts[i - 1][0], r.pts[i - 1][1], O), q = proj(r.pts[i][0], r.pts[i][1], O);
            if (Math.hypot(q.x - p.x, q.z - p.z) < 0.5) {
              out.push(r.id + ': points ' + i + ' on top of each other');
              break;
            }
          }
          return out;
        })"""
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_every_tree_house_and_sight_stands_in_the_ground(page: Page, live_server):
    # the ground as drawn is flat between the terrain's vertices, tens of metres apart: set on the shape those vertices
    # sample rather than on the ground itself, a tree or a house hangs in the air where the ground dips under it
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildWorld === 'function'")
    faults = page.evaluate(
        """() => {
          if (!scene) { // a browser without 3D still builds the scene
            scene = new THREE.Scene(); renderer = { capabilities: { getMaxAnisotropy: () => 1 } }; makeMaterials();
          }
          const ray = new THREE.Raycaster(), down = new THREE.Vector3(0, -1, 0), m = new THREE.Matrix4();
          const p = new THREE.Vector3(), q = new THREE.Quaternion(), k = new THREE.Vector3();
          return ROUTES.flatMap(r => {
            buildWorld(r);
            const out = [], kids = scenery.children;
            const land = kids.find(o => o.isMesh && o.geometry.type === 'PlaneGeometry' && o.material.vertexColors);
            const at = (x, z) => {
              ray.set(new THREE.Vector3(x, 1e5, z), down);
              const hit = ray.intersectObject(land, false)[0];
              return hit ? hit.point.y : null;
            };
            const high = (what, base, x, z) => {
              const g = at(x, z);
              if (g != null && base > g + 1e-3) out.push(r.id + ': ' + what + ' ' + (base - g).toFixed(2) + ' m up');
            };
            // by name: a power line's towers and arms are cylinders and boxes too
            const each = (name, n, f) => {
              const mesh = kids.find(o => o.isInstancedMesh && o.name === name);
              if (!mesh) return;
              const step = Math.max(1, Math.floor(mesh.count / n));
              for (let i = 0; i < mesh.count; i += step) { mesh.getMatrixAt(i, m); m.decompose(p, q, k); f(); }
            };
            each('trunks', 40, () => high('a tree', p.y, p.x, p.z));
            each('houses', 30, () => {
              for (const [a, b] of [[-.5, -.5], [-.5, .5], [.5, -.5], [.5, .5]]) {
                const c = new THREE.Vector3(a * k.x, 0, b * k.z).applyQuaternion(q).add(p);
                high('a house', p.y, c.x, c.z);
              }
            });
            const placed = o => world.lms.some(l => l.x === o.position.x && l.z === o.position.z);
            const sights = kids.filter(o => o.isGroup && placed(o));
            // a sight that spreads over the land -- a cable car, ski jumps -- stands on each of the parts it marks;
            // any other on the lowest of its whole floor plan
            const standing = G => G.userData.spread ? G.children.filter(m => m.userData.stands) : [G];
            sights.forEach(G => standing(G).forEach(part => {
              const box = new THREE.Box3().setFromObject(part), w = box.max.x - box.min.x, d = box.max.z - box.min.z;
              for (let i = 0; i <= 4; i++) for (let j = 0; j <= 4; j++) {
                high('a sight', box.min.y, box.min.x + w * i / 4, box.min.z + d * j / 4);
              }
            }));
            return out;
          });
        }"""
    )
    assert not faults, faults


@pytest.mark.django_db(transaction=True)
def test_no_tree_stands_on_a_road_or_its_shoulder(page: Page, live_server):
    # measured to the route itself: its coarse points are 32 m apart, and a bend between two of them looked far away
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildWorld === 'function'")
    close = page.evaluate(
        """() => {
          if (!scene) { // a browser without 3D still builds the scene
            scene = new THREE.Scene(); renderer = { capabilities: { getMaxAnisotropy: () => 1 } }; makeMaterials();
          }
          const m = new THREE.Matrix4(), p = new THREE.Vector3();
          return ROUTES.flatMap(r => {
            const T = buildWorld(r).T, out = [];
            const trunks = scenery.children.find(o => o.isInstancedMesh && o.geometry.type === 'CylinderGeometry');
            for (let i = 0; i < trunks.count; i++) {
              trunks.getMatrixAt(i, m); p.setFromMatrixPosition(m);
              let gap = Infinity;
              for (let j = 0; j < T.N; j++) gap = Math.min(gap, Math.hypot(T.X[j] - p.x, T.Z[j] - p.z));
              if (gap < r.width / 2 + 2.5) out.push(r.id + ': a tree ' + gap.toFixed(1) + ' m from the route');
            }
            return out;
          });
        }"""
    )
    assert not close, close


@pytest.mark.django_db(transaction=True)
def test_a_road_ridden_out_and_back_is_drawn_once_and_finishes_at_its_start(page: Page, live_server):
    # the way back runs on the road the way out drew: drawn again at the same height, the two would flicker
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=en")
    page.wait_for_function("typeof ROUTES !== 'undefined' && typeof buildWorld === 'function'")
    found = page.evaluate(
        """() => {
          if (!scene) { // a browser without 3D still builds the scene
            scene = new THREE.Scene(); renderer = { capabilities: { getMaxAnisotropy: () => 1 } }; makeMaterials();
          }
          const ray = new THREE.Raycaster(), down = new THREE.Vector3(0, -1, 0), o = {};
          return ROUTES.map(r => {
            const w = buildWorld(r), T = w.T, kids = scenery.children;
            const road = kids.filter(m => m.isMesh && m.geometry.type === 'BufferGeometry' && m.material.map);
            let twice = 0;
            for (let s = 50; s < T.L; s += 100) {
              sampleAt(T, s, o); ray.set(new THREE.Vector3(o.x, o.y + 50, o.z), down);
              const ys = ray.intersectObjects(road, false).map(h => h.point.y).sort((a, b) => a - b);
              if (ys.some((y, i) => i && y - ys[i - 1] < .005)) twice++;
            }
            const arches = kids.filter(g => g.isGroup && g.children.some(c => c.material && c.material.length)).length;
            return { id: r.id, twice, back: w.back, finish: w.FIN, end: T.L - w.S0, arches };
          });
        }"""
    )
    back = [route for route in found if route["back"]]
    assert back, found  # a route out and back is on the maps
    assert [route["twice"] for route in found] == [0] * len(found), found
    # it finishes on its start's line, under one arch for both
    assert all(route["finish"] == pytest.approx(route["end"]) and route["arches"] == 1 for route in back), back


@pytest.mark.django_db(transaction=True)
def test_open_full_screen_puts_the_trainer_on_the_whole_screen(page: Page, live_server):
    page.goto(f"{live_server.url}/en/virtual-ride/")
    if not page.evaluate("!!(document.fullscreenEnabled || document.webkitFullscreenEnabled)"):
        pytest.skip("this browser gives a frame no full screen")
    pages = len(page.context.pages)
    page.get_by_role("link", name="Open full screen").click()
    page.wait_for_function("() => document.fullscreenElement === document.querySelector('.virtual-ride-frame')")
    assert len(page.context.pages) == pages  # the trainer stays in the site's page, on the whole screen
    # the trainer's keys reach it
    assert page.evaluate("document.activeElement === document.querySelector('.virtual-ride-frame')")
    page.evaluate("document.exitFullscreen()")  # what Escape does
    page.wait_for_function("() => document.fullscreenElement === null")


@pytest.mark.django_db(transaction=True)
def test_where_a_frame_cannot_go_full_screen_the_trainer_opens_on_a_page_of_its_own(page: Page, live_server):
    # an iPhone gives a frame no full screen
    page.add_init_script(
        "for (const name of ['fullscreenEnabled', 'webkitFullscreenEnabled'])"
        " Object.defineProperty(Document.prototype, name, { get: () => false, configurable: true });"
    )
    page.goto(f"{live_server.url}/en/virtual-ride/")
    with page.context.expect_page() as opened:
        page.get_by_role("link", name="Open full screen").click()
    assert "/static/trainer/alatau.html?" in opened.value.url
    assert page.evaluate("document.fullscreenElement") is None


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
        '<p id="mpStatus"></p><div id="mpOnline"></div><div id="mpGroups"></div>'
        '<select id="mpDelay"><option value="60"></option></select><button id="mpCreate"></button>'
        '<button id="mpEvent"></button>'
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
            const groupWind = () => null; // a race in still air
            const mpClash = () => false, MP_HOUR = 3600e3, LOCALE = 'en-GB'; // starting within the hour
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
    "GET /api/v1/virtual-ride/events",  # the member's own events a race with protocols may be made for
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


def _settled(rho: float, cda: float, g: float, tail: float = 0.0) -> float:
    """The speed at which 200 W meets the drag on the flat: rider and bike of 83 kg, Crr .004, the air dragging by
    the speed through it -- a wind of ``tail`` m/s behind the rider, ahead when below zero."""
    lo, hi = 0.0, 30.0
    for _ in range(60):
        mid, air = (lo + hi) / 2, (lo + hi) / 2 - tail
        lo, hi = (mid, hi) if mid * (rho * cda * air * abs(air) / 2 + 0.004 * 83 * g) < 200 else (lo, mid)
    return lo


def test_a_headwind_slows_the_rider_and_a_tailwind_carries_them(page: Page):
    """On the flat road north, 200 W in a wind of 5 m/s: from the north it is ahead of the rider, from the south
    behind them, from the east beside them, which the ride leaves out."""
    errors = _ride_alone(page)
    speeds, rho, g = page.evaluate(
        """() => {
            const inp = { P: 200, cad: 85, mode: 'power', direct: false };
            const speeds = [0, null, 180, 90].map(from => {
                rideWind = from === null ? null : { ms: 5, from }; me.v = 0; me.s = world.S0;
                for (let i = 1; i <= 240 * 60; i++) stepRide(1 / 60, inp, i / 60);
                return me.v;
            });
            return [speeds, me.rho, PHYS.g];
        }"""
    )
    ahead, still, behind, beside = speeds
    assert ahead == pytest.approx(_settled(rho, 0.3, g, tail=-5), abs=0.01)
    assert still == pytest.approx(_settled(rho, 0.3, g), abs=0.01)
    assert behind == pytest.approx(_settled(rho, 0.3, g, tail=5), abs=0.01)
    assert beside == pytest.approx(still, abs=0.01)
    assert errors == [], errors


def test_a_smart_trainer_is_told_the_wind_against_the_rider(page: Page):
    _ride_alone(page)
    winds = page.evaluate(
        f"""() => [0, 180].map(from => {{
            rideWind = {{ ms: 4, from }}; stepRide(1 / 60, {_STILL}, 0); return trainerDrag(me).wind;
        }})"""
    )
    # a headwind above zero, as ANT+ FE-C has it: on the road north the wind from the north is ahead
    assert winds == pytest.approx([4, -4])


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
            // riders of one size, as the measurements had them (another size: the test after the bot's below)
            const other = newRider('other', 0, 75, 0, 2); other.remote = true; other.CdA = me.CdA; bots = [other];
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
            const ahead = newRider('ahead', 0, 75, me.s + 2.41, me.lane); ahead.remote = true; ahead.CdA = me.CdA;
            bots = [ahead];
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
            Object.assign(bot, {{ ch: {{ style: 'rouleur' }}, wkg: 3, seed: 1, CdA: me.CdA }}); bots = [bot];
            stepRide(1 / 60, {_STILL}, 0); return bot.draft;
        }}"""
    )
    assert share == pytest.approx(0.45, abs=1e-3)
    assert errors == [], errors


def test_whom_a_rider_hides_behind_changes_the_wake(page: Page):
    """45 % of the drag saved 0.7 m behind a rider of one's own size; more behind a bigger one, less behind a
    smaller one, by the square root of their drag areas and within 0.8 to 1.2 of it."""
    errors = _ride_alone(page)
    shares = page.evaluate(
        f"""() => {{
            globalThis.mpStepRemote = () => {{}};
            me.CdA = .32;
            const ahead = newRider('ahead', 0, 75, me.s + 1.71 + .7, me.lane); ahead.remote = true; bots = [ahead];
            const behind = cda => {{ ahead.CdA = cda; stepRide(1 / 60, {_STILL}, 0); return me.draft; }};
            // one's own size; a small rider on a TT bike; a big one on an MTB; a tiny one and a huge one
            return [behind(.32), behind(.22), behind(.45), behind(.1), behind(1)];
        }}"""
    )
    assert shares == pytest.approx([0.45, 0.373, 0.534, 0.36, 0.54], abs=1e-3)
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
            Object.assign(me, {{ CdA: .35, Crr: .0058 }}); ahead.CdA = me.CdA;
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


def test_a_trainer_that_does_not_ride_the_route_says_why(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    troubles = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // a trainer under control that answers the grade with `code`, as FTMS answers: 3 is Invalid Parameter
            let code = 3;
            const trainer = new BLEDev({ name: 'trainer' });
            trainer.ctrl = true; trainer.status = 'online'; trainer.roles.add('trainer'); trainer.cpt = {};
            trainer.write = async bytes => {
                setTimeout(() => trainer.onCtrl(new DataView(new Uint8Array([0x80, bytes[0], code]).buffer)), 0);
            };
            const settle = () => new Promise(done => setTimeout(done, 50)), troubles = [Trainer.trouble()];
            Sensors.devs.push(trainer);
            Trainer.update(10, 4, me); await settle(); troubles.push(Trainer.trouble());
            code = 1; Trainer.update(11, 4, me); await settle(); troubles.push(Trainer.trouble());
            trainer.ctrl = false; troubles.push(Trainer.trouble());
            trainer.status = 'reconnecting'; troubles.push(Trainer.trouble());
            return troubles;
        }"""
    )
    # none connected; the grade refused; taken; control gone to another app; away for a moment (said as lost)
    assert troubles == [None, "refused", None, "control", None], troubles
    assert errors == [], errors


def test_a_bike_that_only_sends_its_data_is_not_said_to_be_off_the_route(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    state = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // FTMS bike data and no control point: a spin bike whose resistance is a knob
            const bikeData = { addEventListener() {}, async startNotifications() {} };
            const ftms = {
                async getCharacteristic(uuid) { if (uuid === 0x2AD2) return bikeData; throw new Error('-'); } };
            const server = {
                async getPrimaryService(uuid) { if (uuid === 0x1826) return ftms; throw new Error('-'); } };
            const gatt = { async connect() { return server; } };
            const bike = new BLEDev({ name: 'bike', addEventListener() {}, gatt });
            Sensors.devs.push(bike); await bike.connect();
            return { trainer: bike.roles.has('trainer'), ctrl: bike.ctrl, trouble: Trainer.trouble() };
        }"""
    )
    # ridden by its power, not driven, and nothing to put right: no warning
    assert state == {"trainer": True, "ctrl": False, "trouble": None}, state
    assert errors == [], errors


def test_a_refusal_is_the_connection_s_that_made_it(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    troubles = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // a trainer that gives control and starts, and answers the grade with `code` (3: Invalid Parameter)
            const trainerAnswering = code => {
                const point = { listeners: [], addEventListener(name, fn) { this.listeners.push(fn); },
                    async startNotifications() {},
                    async writeValueWithResponse(data) {
                        const op = data[0], answer = op === 0x11 ? code : 1;
                        const value = new DataView(new Uint8Array([0x80, op, answer]).buffer);
                        setTimeout(() => this.listeners.forEach(fn => fn({ target: { value } })), 0);
                    } };
                const bikeData = { addEventListener() {}, async startNotifications() {} };
                const ftms = { async getCharacteristic(uuid) {
                    if (uuid === 0x2AD9) return point; if (uuid === 0x2AD2) return bikeData; throw new Error('-'); } };
                const server = {
                    async getPrimaryService(uuid) { if (uuid === 0x1826) return ftms; throw new Error('-'); } };
                const gatt = { async connect() { return server; } };
                return new BLEDev({ name: 'trainer', addEventListener() {}, gatt });
            };
            const settle = () => new Promise(done => setTimeout(done, 50)), troubles = [];
            const first = trainerAnswering(3); Sensors.devs.push(first); await first.connect();
            Trainer.update(10, 4, me); await settle(); troubles.push(Trainer.trouble());
            await first.connect(); troubles.push(Trainer.trouble());
            Sensors.devs = [trainerAnswering(1)]; await Sensors.devs[0].connect(); troubles.push(Trainer.trouble());
            return troubles;
        }"""
    )
    # the grade refused; the same trainer connected again, and another one, have refused nothing yet
    assert troubles == ["refused", None, None], troubles
    assert errors == [], errors


def test_a_trainer_that_holds_a_workout_s_power_is_not_said_to_be_off_the_route(page: Page):
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=trainer_page.PAGE.parent / "alatau" / name)
    troubles = page.evaluate(
        """async () => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
            // a trainer that holds a power (FTMS Set Target Power) and refuses the grade (Invalid Parameter)
            const trainer = new BLEDev({ name: 'trainer' });
            trainer.ctrl = true; trainer.status = 'online'; trainer.roles.add('trainer'); trainer.cpt = {};
            trainer.ergRange = [0, 2000];
            trainer.write = async bytes => {
                const code = bytes[0] === 0x05 ? 1 : 3;
                setTimeout(() => trainer.onCtrl(new DataView(new Uint8Array([0x80, bytes[0], code]).buffer)), 0);
            };
            Sensors.devs.push(trainer);
            const settle = () => new Promise(done => setTimeout(done, 50)), troubles = [];
            Trainer.update(10, 4, me, null); await settle(); troubles.push(Trainer.trouble());
            Trainer.update(11, 4, me, 200); await settle(); troubles.push(Trainer.trouble());
            Trainer.update(12, 4, me, null); await settle(); troubles.push(Trainer.trouble());
            return troubles;
        }"""
    )
    # the grade refused; a workout step's 200 W held, as the rider asked; the grade refused again
    assert troubles == ["refused", None, "refused"], troubles
    assert errors == [], errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_ride_on_a_trainer_that_gave_no_control_says_so_in_words(page: Page, live_server, lang: str):
    """The small "gradient" in place of "trainer 2 %" was all a rider was told, and they pedalled a resistance that
    was not the route's."""
    _trainer_in_its_menu(page, live_server, lang)
    page.evaluate(
        """() => {
            // a trainer that sends its power but gave its control to another app; a race alone, which has no
            // message of its own at the start (a free ride says how to end it 4.5 s in)
            const trainer = new BLEDev({ name: 'trainer' });
            trainer.status = 'online'; trainer.cpt = {}; trainer.roles.add('trainer'); trainer.roles.add('power');
            Sensors.devs.push(trainer); settings.mode = 'race'; $('#bots').value = '0'; startRace();
        }"""
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")  # the HUD is drawn every tenth of a second
    line, said = page.evaluate("[t('hud.trainerIdle'), t('bt.trainerNoCtrl')]")
    expect(page.locator("#hudTrainer")).to_be_visible()
    expect(page.locator("#hudTrainer")).to_have_text(line)
    expect(page.locator("#toast")).to_have_text(said)
    # within its card, in every language: nothing cut off or spilling over
    fits = page.evaluate(
        """() => { const el = document.querySelector('#hudTrainer'), box = el.getBoundingClientRect(),
            card = el.closest('.mapcard').getBoundingClientRect();
            return el.scrollWidth <= el.clientWidth && box.right <= card.right; }"""
    )
    assert fits
    # readable over the lightest sky: the scene is drawn on a canvas no contrast reading sees, so a white page stands
    # under the see-through card for it (amber letters on the card read at 2:1 there; dark ink on amber at 8:1)
    page.evaluate("() => { document.documentElement.style.background = document.body.style.background = '#fff'; }")
    assert contrast.legibility(page.locator("#hudTrainer")) >= 4.5
    # given control again and riding the route, the line goes
    page.evaluate("() => { Sensors.trainer().ctrl = true; Trainer.sent = 0; drawFrame(200); }")
    expect(page.locator("#hudTrainer")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_each_ride_on_a_trainer_without_control_says_why_once(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        """() => {
            // a race alone: no message of its own at the start to stand in for the one looked for
            const trainer = new BLEDev({ name: 'trainer' });
            trainer.status = 'online'; trainer.cpt = {}; trainer.roles.add('trainer'); trainer.roles.add('power');
            Sensors.devs.push(trainer); settings.mode = 'race'; $('#bots').value = '0'; startRace();
        }"""
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    said = page.evaluate("t('bt.trainerNoCtrl')")
    page.evaluate("drawFrame(200)")
    expect(page.locator("#toast")).to_have_text(said)
    # once: the frames after it leave another message in its place
    page.evaluate("() => { toast('another', 3); drawFrame(200); }")
    expect(page.locator("#toast")).to_have_text("another")
    # the next ride says it again, once the message on screen is gone rather than over it
    page.evaluate("() => { startMenu(); startRace(); }")
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("() => { toast('another', 3); drawFrame(200); }")
    expect(page.locator("#toast")).to_have_text("another")
    page.evaluate("() => { for (let i = 0; i < 7; i++) drawFrame(500); }")
    expect(page.locator("#toast")).to_have_text(said)


@pytest.mark.django_db(transaction=True)
def test_a_trainer_whose_refusals_come_and_go_is_said_once_a_ride(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        """() => {
            const trainer = new BLEDev({ name: 'trainer' });
            trainer.status = 'online'; trainer.ctrl = true; trainer.cpt = {};
            trainer.roles.add('trainer'); trainer.roles.add('power');
            Sensors.devs.push(trainer); settings.mode = 'free'; startRace();
        }"""
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    said = page.evaluate(
        """() => {
            const said = [], trainer = Sensors.trainer(), was = toast;
            toast = (text, d) => { said.push(text); was(text, d); };
            // a trainer that refuses some grades and takes others: its refusal comes and goes
            for (const refused of [true, false, true, false, true]) {
                trainer.refused = refused;
                for (let i = 0; i < 20; i++) drawFrame(500); // ten seconds: any message on screen is gone
            }
            toast = was;
            return said.filter(text => text === t('dev.refusedGrade')).length;
        }"""
    )
    assert said == 1, said


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


# The trainer's frame on a 320 px phone: the site page's margins leave it 296 px.
_PHONE_FRAME: ViewportSize = {"width": 296, "height": 700}
# How far the setup scrolls sideways, and what sticks out of it, named for a failure's message.
_SIDEWAYS = """() => {
  const setup = document.querySelector('.setup'), edge = setup.getBoundingClientRect();
  const out = [...setup.querySelectorAll('*')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && (r.right > edge.right + 0.5 || r.left < edge.left - 0.5);
  }).map(e => e.tagName + '#' + e.id + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right));
  return [setup.scrollWidth, setup.clientWidth, out.slice(0, 5)];
}"""


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
            const high = Object.assign({}, flat, { id: 'high' });
            addMap({ id: 'steppe', name: named, origin: { lat: 51.16, lon: 71.43 }, routes: [flat] });
            addMap({ id: 'foothills', name: named, origin: { lat: 51.16, lon: 71.43 }, mountains: { south: 20000 },
                     routes: [high] });
            const wide = o => o.name === 'range'; // addMountains
            const range = id => {
                buildWorld(ROUTES.find(r => r.id === id));
                let n = 0; scenery.traverse(o => { if (wide(o)) n++; }); return n;
            };
            return { foothills: range('high'), steppe: range('flat') };
        }"""
    )
    assert ranges == {"foothills": 1, "steppe": 0}


@pytest.mark.django_db(transaction=True)
def test_a_range_runs_on_past_where_the_view_reaches(page: Page, live_server):
    """Ridden back towards Kyrbaltabay, the range ended in view on the left: 90 km long, it stopped 45 km east of the
    origin while the real one goes on. A map without its relief raises one 150 km either way now."""
    _trainer_in_its_menu(page, live_server)
    reach = page.evaluate(
        """() => {
            const named = { ru: 'n', kk: 'n', en: 'n' };
            const road = { id: 'road', name: named, desc: named, loop: false, width: 8, lanes: 2, scenery: 'steppe',
                           pts: [[43.6, 77.4, 550], [43.6, 77.4124, 550]] };
            addMap({ id: 'plain', name: named, origin: { lat: 43.6, lon: 77.4 }, mountains: { south: 30000 },
                     routes: [road] });
            buildWorld(ROUTES.find(r => r.id === 'road'));
            const range = scenery.children.find(o => o.name === 'range');
            range.geometry.computeBoundingBox();
            const box = range.geometry.boundingBox;
            return [Math.round(box.min.x / 1000), Math.round(box.max.x / 1000)];
        }"""
    )
    assert reach[0] <= -150 and reach[1] >= 150, reach


@pytest.mark.django_db(transaction=True)
def test_a_map_s_relief_stands_where_srtm_has_it_and_sinks_under_the_scenery_s_ground(page: Page, live_server):
    """The land beyond the scenery is the map's SRTM relief: the snowy range where it really rises, south of
    Kyrbaltabay, lowered by the Earth's curve, going on past where the view reaches; under the scenery's own
    ground it sinks out of the way, so the near ground and its trees are the scenery's."""
    _trainer_in_its_menu(page, live_server)
    seen = page.evaluate(
        """() => {
            const T = buildWorld(ROUTES.find(r => r.id === 'kyrbaltabay-tuganbay')).T;
            const relief = scenery.children.find(o => o.name === 'relief'), a = relief.geometry.attributes.position;
            let poking = 0, top = { y: -1e9, z: 0 }, minX = 1e9, maxX = -1e9;
            const x0 = T.minX - 1600, x1 = T.maxX + 1600, z0 = T.minZ - 1600, z1 = T.maxZ + 1600;
            for (let i = 0; i < a.count; i++) {
                const x = a.getX(i), y = a.getY(i), z = a.getZ(i);
                if (x > x0 && x < x1 && z > z0 && z < z1 && y > T.minY - 39) poking++;
                if (y > top.y) top = { y, z };
                minX = Math.min(minX, x); maxX = Math.max(maxX, x);
            }
            const ranges = scenery.children.filter(o => o.name === 'range').length;
            return { poking, top: Math.round(top.y), south: Math.round(top.z / 1000), west: Math.round(minX / 1000),
                     east: Math.round(maxX / 1000), ranges };
        }"""
    )
    assert seen["poking"] == 0 and seen["ranges"] == 0, seen
    assert seen["top"] > 3000 and seen["south"] > 20, seen
    assert seen["west"] < -100 and seen["east"] > 100, seen


@pytest.mark.django_db(transaction=True)
def test_a_route_far_from_its_map_s_others_is_drawn_from_its_own_origin_and_range(page: Page, live_server):
    """A region's routes lie tens of kilometres apart: one far from the map's origin carries its own, and its own
    mountains, so its road starts near the scene's middle and its range rises south of it, not of the map's."""
    _trainer_in_its_menu(page, live_server)
    drawn = page.evaluate(
        """() => {
            const named = { ru: 'n', kk: 'n', en: 'n' };
            const road = (id, lon, extra) => Object.assign({ id, name: named, desc: named, loop: false, width: 9,
                lanes: 2, scenery: 'steppe', pts: [[43.6, lon, 600], [43.6, lon + 0.0124, 600]] }, extra);
            const far = { origin: { lat: 43.6, lon: 76.5 }, mountains: { south: 30000 } };
            addMap({ id: 'region', name: named, origin: { lat: 43.6, lon: 77.4 },
                     routes: [road('near', 77.4), road('far', 76.5, far)] });
            const wide = o => o.name === 'range'; // addMountains
            const drawnOn = id => {
                const T = buildWorld(ROUTES.find(r => r.id === id)).T;
                let ranges = 0; scenery.traverse(o => { if (wide(o)) ranges++; });
                return { origin: T.origin, start: Math.round(Math.hypot(T.X[0], T.Z[0])), ranges };
            };
            return { near: drawnOn('near'), far: drawnOn('far') };
        }"""
    )
    assert drawn["near"] == {"origin": {"lat": 43.6, "lon": 77.4}, "start": 0, "ranges": 0}
    assert drawn["far"] == {"origin": {"lat": 43.6, "lon": 76.5}, "start": 0, "ranges": 1}


@pytest.mark.django_db(transaction=True)
def test_a_racetrack_keeps_its_edges_clear_and_its_one_lane_has_no_centre_line(page: Page, live_server):
    """A racetrack lies in the steppe, its edges run-off and barriers: its trees stand out in the grass only, and a road
    of one lane, as a racetrack is, has no line down its middle."""
    _trainer_in_its_menu(page, live_server)
    seen = page.evaluate(
        """() => {
            const named = { ru: 'n', kk: 'n', en: 'n' }, ring = [];
            for (let i = 0; i < 40; i++) {
                const a = i / 40 * 2 * Math.PI;
                ring.push([43.6 + 0.006 * Math.sin(a), 76.5 + 0.008 * Math.cos(a), 650]);
            }
            const lap = (id, scenery) => ({ id, name: named, desc: named, loop: true, width: 12, lanes: 1, scenery,
                                           pts: ring });
            addMap({ id: 'circuit', name: named, origin: { lat: 43.6, lon: 76.5 },
                     routes: [lap('track', 'racetrack'), lap('road', 'steppe')] });
            const m = new THREE.Matrix4(), p = new THREE.Vector3();
            const nearestTree = id => {
                const T = buildWorld(ROUTES.find(r => r.id === id)).T;
                const trunks = scenery.children.find(o => o.isInstancedMesh && o.geometry.type === 'CylinderGeometry');
                let gap = Infinity;
                for (let i = 0; i < trunks.count; i++) {
                    trunks.getMatrixAt(i, m); p.setFromMatrixPosition(m);
                    for (let j = 0; j < T.N; j++) gap = Math.min(gap, Math.hypot(T.X[j] - p.x, T.Z[j] - p.z));
                }
                return Math.round(gap);
            };
            const middle = lanes => { // the texture's colour in the middle of the road, near its top
                const pixel = roadTexture(lanes).image.getContext('2d').getImageData(128, 10, 1, 1).data;
                return [...pixel].slice(0, 3);
            };
            return { track: nearestTree('track'), road: nearestTree('road'), one: middle(1), two: middle(2) };
        }"""
    )
    assert seen["track"] > 30 > seen["road"], seen
    assert max(seen["one"]) < 150 < min(seen["two"]), seen


@pytest.mark.django_db(transaction=True)
def test_a_racetrack_s_barriers_break_at_its_buildings_and_its_trees_grow_where_mapped(page: Page, live_server):
    """A route's own scenery: its guardrail and catch fence run a gap beyond each edge and break where a building
    stands, the building is drawn from its footprint, and its trees grow along the rows the map gives, nowhere else."""
    _trainer_in_its_menu(page, live_server)
    seen = page.evaluate(
        """() => {
            const named = { ru: 'n', kk: 'n', en: 'n' }, ring = [];
            for (let i = 0; i < 40; i++) {
                const a = i / 40 * 2 * Math.PI;
                ring.push([43.6 + 0.006 * Math.sin(a), 76.5 + 0.008 * Math.cos(a), 650]);
            }
            // a building by the ring's east point, its near wall 12.5 m from the middle of the road, 40 m long
            const m = 1 / (111320 * Math.cos(43.6 * Math.PI / 180)), n = 1 / 111195, e = 76.508;
            const box = [[43.6 - 20 * n, e + 12.5 * m], [43.6 - 20 * n, e + 40 * m], [43.6 + 20 * n, e + 40 * m],
                         [43.6 + 20 * n, e + 12.5 * m]];
            const route = { id: 'lap', name: named, desc: named, loop: true, width: 12, lanes: 1, scenery: 'racetrack',
                            pts: ring, barriers: { gap: 6 }, buildings: [{ h: 8, pts: box }],
                            trees: { rows: [[[43.615, 76.49], [43.615, 76.56]]] } }; // on 4 km past the drawn ground
            addMap({ id: 'circuit', name: named, origin: { lat: 43.6, lon: 76.5 }, routes: [route] });
            const T = buildWorld(ROUTES.find(r => r.id === 'lap')).T;
            const verts = name => {
                const mesh = scenery.children.find(o => o.name === name), out = [];
                const a = mesh.geometry.attributes.position;
                for (let i = 0; i < a.count; i++) out.push([a.getX(i), a.getZ(i)]);
                return out;
            };
            const foot = box.map(p => { const q = proj(p[0], p[1], T.origin); return [q.x, q.z]; });
            const barrier = verts('rail').concat(verts('fence'));
            const trunks = scenery.children.find(o => o.isInstancedMesh && o.geometry.type === 'CylinderGeometry');
            const mx = new THREE.Matrix4(), p = new THREE.Vector3(), row = proj(43.615, 76.5, T.origin).z;
            let offRow = 0, farthest = 0;
            for (let i = 0; i < trunks.count; i++) {
                trunks.getMatrixAt(i, mx); p.setFromMatrixPosition(mx); if (Math.abs(p.z - row) > 1) offRow++;
                farthest = Math.max(farthest, routeGap(T, p.x, p.z));
            }
            return {
                nearest: Math.min(...verts('rail').map(([x, z]) => routeGap(T, x, z))),
                atBuilding: barrier.filter(([x, z]) => insideRing(foot, x, z) || ringGap(foot, x, z) < 1.9).length,
                drawn: world_osmKept, trees: trunks.count, offRow, farthest: Math.round(farthest),
            };
        }"""
    )
    assert seen["nearest"] > 12 - 1.01, seen
    assert seen["atBuilding"] == 0 and seen["drawn"] == 1, seen
    assert seen["trees"] > 100 and seen["offRow"] == 0 and seen["farthest"] <= 1500, seen


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
    almaty = cities.get_by_role("button", name="Almaty", exact=True)  # not Almaty Region
    steppe = cities.get_by_role("button", name="Steppe")
    expect(almaty).to_have_attribute("aria-pressed", "true")
    steppe.click()
    expect(steppe).to_have_attribute("aria-pressed", "true")
    expect(almaty).to_have_attribute("aria-pressed", "false")
    expect(routes).to_have_text(["east", "west"])
    assert page.evaluate("routeSel") == "east"
    almaty.click()
    expect(routes).to_have_text(["Central loop", "Climb to Medeu", "Old centre", "Al-Farabi sprint", "Granfondo 2026"])
    assert page.evaluate("routeSel") == "center"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [360, 320])
def test_a_city_s_button_is_big_enough_to_tap_on_a_phone(page: Page, live_server, width: int):
    """A slim pill, tapped across 44 px: its zone reaches past its frame, and the rows keep apart so two zones
    never meet (the interface rules, 9). Each city's is measured, the ones coming soon too."""
    page.set_viewport_size({"width": width, "height": 740})
    _trainer_in_its_menu(page, live_server)
    cities = page.locator("#cities .city")
    expect(cities).to_have_count(len(trainer_page.maps()))
    for city in cities.all():
        city.scroll_into_view_if_needed()
        wide, high = city.evaluate(_REACH)
        assert wide >= 44 and high >= 44, (city.text_content(), wide, high)


@pytest.mark.django_db(transaction=True)
def test_add_event_gathers_the_race_and_opens_the_event_form_filled_from_the_route(page: Page, live_server):
    rider = User.objects.create_user(
        username="e2e_vr_event", email="e2e_vr_event@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    # the lists as the migrations seed them -- laid again where a test before this one emptied the tables
    virtual, _ = EventType.objects.get_or_create(name_en="Virtual Ride", defaults={"name_ru": "Virtual", "order": 1})
    road, _ = DisciplineCategory.objects.get_or_create(name_en="Road Cycling", defaults={"name_ru": "Road", "order": 1})
    coffee, _ = Discipline.objects.get_or_create(
        name_en="Coffee Ride", category=road, defaults={"name_ru": "Coffee Ride", "order": 1}
    )
    inject_session(page, live_server, rider)
    page.goto(f"{live_server.url}/en/virtual-ride/")
    frame = page.frame_locator("iframe.virtual-ride-frame")
    page.wait_for_load_state("networkidle")
    if not frame.locator("html").evaluate("() => typeof phase !== 'undefined' && phase === 'menu'"):
        pytest.skip("this browser cannot draw 3D, so the trainer stops before its menu")
    expect(frame.locator("#mpCreate")).to_be_enabled()  # the lobby answered: the member rides together
    frame.locator("#mpDelay").select_option("at")
    # tomorrow at seven in the evening, on the member's own clock
    day = frame.locator("html").evaluate(
        "() => { const d = new Date(Date.now() + 864e5), p = n => String(n).padStart(2, '0');"
        " return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); }"
    )
    frame.locator("#mpDate").fill(day)
    frame.locator("#mpTime").fill("19:00")
    with page.expect_navigation(url=re.compile(r"/en/calendar/submit/\?draft=1$")):
        frame.locator("#mpEvent").click()
    race = GroupRide.objects.get(host=rider)
    assert race.route == "center"
    expect(page.locator("#id_title_en")).to_have_value("Virtual group race: Central loop")
    expect(page.locator("#id_title_ru")).to_have_value(re.compile(r"\S"))
    expect(page.locator("#id_date_start")).to_have_value(day)
    description = page.locator("#id_description_en").input_value()
    assert f"{live_server.url}/en/virtual-ride/?group={race.pk}" in description, description
    assert "19:00 (UTC" in description and "{" not in description, description
    assert f"/kk/virtual-ride/?group={race.pk}" in page.locator("#id_description_kk").input_value()
    types = page.locator("#id_event_types option:checked").evaluate_all("options => options.map(o => +o.value)")
    assert types == [virtual.pk], types
    chosen = page.evaluate("() => JSON.parse(document.getElementById('disc-selected-data').textContent)")
    assert chosen == [coffee.pk], chosen


@pytest.mark.django_db(transaction=True)
def test_the_wind_is_kept_with_the_settings_and_named_before_the_start(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#windOpts")).to_be_hidden()
    page.check("#windOn")
    expect(page.locator("#windOpts")).to_be_visible()
    page.select_option("#windFrom", "270")
    page.fill("#windMs", "7")
    page.locator("#windMs").dispatch_event("change")
    assert page.evaluate("store.get('settings', {}).wind") == {"on": True, "from": 270, "ms": 7}
    # kept for the next visit, as the other settings are (and with the account, for a member)
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("#windOn")).to_be_checked()
    expect(page.locator("#windFrom")).to_have_value("270")
    expect(page.locator("#windMs")).to_have_value("7")
    expect(page.locator("#startSum")).to_contain_text("wind 7 m/s from the west")


@pytest.mark.django_db(transaction=True)
def test_a_box_is_ticked_from_its_box_and_words_not_from_the_empty_row_beside_them(page: Page, live_server):
    """The wind's row stretched across the setup page: a click far from the word "Wind" turned it on, and a rider rode
    in a 5 m/s wind they never chose."""
    page.set_viewport_size({"width": 1512, "height": 945})  # a laptop's, where the row was 1082 px for 66 px of words
    _trainer_in_its_menu(page, live_server)
    # every box on the setup page ends where its words do
    overhang = page.evaluate(
        """() => [...document.querySelectorAll('#menu label.chk')].filter(l => l.offsetParent)
            .map(l => l.getBoundingClientRect().right - l.querySelector('span').getBoundingClientRect().right)"""
    )
    assert overhang and max(overhang) <= 1, overhang
    page.locator("#windOn").scroll_into_view_if_needed()
    beside, words = page.evaluate(
        """() => { const s = document.querySelector('#windOn + span').getBoundingClientRect(),
            row = document.querySelector('#windOn').closest('label').parentElement.getBoundingClientRect(),
            y = s.top + s.height / 2;
            return [[s.right + Math.min(200, (row.right - s.right) / 2), y], [s.left + s.width / 2, y]]; }"""
    )
    page.mouse.click(*beside)
    expect(page.locator("#windOn")).not_to_be_checked()
    page.mouse.click(*words)
    expect(page.locator("#windOn")).to_be_checked()


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


@pytest.mark.django_db(transaction=True)
def test_a_finished_plan_rides_on_freely_until_the_rider_ends_it(page: Page, live_server):
    """The plan done, nothing stops the ride, nor saves it or sends it to the services (the maintainer, 2026-11-26):
    it rides on freely, the trainer let go of the plan's power; End the ride saves the workout, its extra time in."""
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        "() => { settings.mode = 'plan'; settings.plan.steps = [{ f: 2, r: 6, cad: 90, min: 0.05 }]; startRace(); }"
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    # four seconds of countdown, the plan's three, then three more
    page.evaluate("() => { for (let i = 0; i < 40; i++) drawFrame(250); }")
    riding = page.evaluate(
        """() => ({ phase, plan: Work.active, power: Work.target(), saved: Records.data.history.length,
                    left: $('#plLeft').textContent, toast: $('#toast').textContent })"""
    )
    words = page.evaluate("[TEXT.en['plan.overLeft'], TEXT.en['plan.over']]")
    assert riding == {"phase": "race", "plan": False, "power": None, "saved": 0, "left": words[0], "toast": words[1]}
    expect(page.locator("#resM")).to_be_hidden()
    page.click("#btnPause")
    page.click("#btnFinish")
    expect(page.locator("#resM")).to_be_visible()
    expect(page.locator("#resTitle")).to_have_text(page.evaluate("TEXT.en['res.workoutDone']"))
    kept = page.evaluate(
        "() => { const h = Records.data.history; return { saved: h.length, kind: h[0].kind, t: h[0].time }; }"
    )
    assert kept["saved"] == 1 and kept["kind"] == "plan" and kept["t"] > 5, kept


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
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_device_s_long_name_never_pushes_the_setup_sideways_on_a_narrow_phone(page: Page, live_server, lang):
    devices = [{"id": "a", "name": "Wahoo KICKR CORE 5D91XXXXLONG"}, {"id": "b", "name": ""}]
    page.add_init_script(f"localStorage.setItem('alatau:devices', {json.dumps(json.dumps(devices))})")
    page.set_viewport_size(_PHONE_FRAME)
    _trainer_in_its_menu(page, live_server, lang)
    wide, room, sticking_out = page.evaluate(_SIDEWAYS)
    assert wide <= room and not sticking_out, (wide, room, sticking_out)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_menu_s_longest_choice_never_pushes_the_setup_sideways_on_a_narrow_phone(page: Page, live_server, lang):
    page.set_viewport_size(_PHONE_FRAME)
    _trainer_in_its_menu(page, live_server, lang)
    page.evaluate(
        "document.querySelectorAll('.setup select').forEach(menu => {"
        " const longest = [...menu.options].sort((a, b) => b.text.length - a.text.length)[0];"
        " if (longest) menu.value = longest.value; })"
    )
    wide, room, sticking_out = page.evaluate(_SIDEWAYS)
    assert wide <= room and not sticking_out, (wide, room, sticking_out)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_route_s_card_and_its_profile_keep_inside_on_a_narrow_phone(page: Page, live_server, lang):
    page.set_viewport_size(_PHONE_FRAME)
    _trainer_in_its_menu(page, live_server, lang)
    # what stands past a card's padding edge, or a section's, named for a failure's message
    too_wide = page.evaluate("""() => {
      const out = [], routes = document.querySelector('#routes');
      if (routes.scrollWidth > routes.clientWidth)
        out.push('routes ' + routes.scrollWidth + ' > ' + routes.clientWidth);
      for (const card of routes.querySelectorAll('.route')) {
        const r = card.getBoundingClientRect(), cs = getComputedStyle(card);
        const edge = r.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth) + 0.5;
        for (const part of card.children) {
          const right = part.getBoundingClientRect().right;
          if (right > edge || part.scrollWidth > part.clientWidth)
            out.push(card.querySelector('b').textContent + ': ' + part.tagName
                     + ' ' + Math.round(right) + ' > ' + Math.round(edge));
        }
      }
      return out;
    }""")
    assert not too_wide, too_wide
