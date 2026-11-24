"""Workouts planned in intervals.icu, ridden on the trainer page by their power (issue #471, phase 2).

The plan screen lists the member's workouts and rides the one picked; a workout's steps set power,
ramps and cues; a smart trainer holds a step's power by ERG while the rider leaves ERG on.
"""

import pytest
from playwright.sync_api import Page, expect

from tests import trainer_page
from tests.e2e.test_virtual_ride import _FRAMES, _ride_alone, _trainer_in_its_menu

_ALATAU = trainer_page.PAGE.parent / "alatau"


def _with_bluetooth(page: Page) -> list[str]:
    errors = _ride_alone(page)
    for name in ("js/i18n.js", "js/bluetooth.js"):
        page.add_script_tag(path=_ALATAU / name)
    page.evaluate(
        """() => {
            globalThis.settings = { difficulty: 100 };
            globalThis.toast = () => {}; globalThis.renderDevs = () => {}; globalThis.updateModeUI = () => {};
        }"""
    )
    return errors


# a trainer under control that answers each command at once, as FTMS asks
_TRAINER = """range => {
    const trainer = new BLEDev({ name: 'trainer' }), sent = [];
    trainer.ctrl = true; trainer.roles.add('trainer'); trainer.ergRange = range;
    trainer.write = async bytes => {
        sent.push(Array.from(bytes));
        setTimeout(() => trainer.onCtrl(new DataView(new Uint8Array([0x80, bytes[0], 1]).buffer)), 5);
    };
    Sensors.devs.push(trainer);
    globalThis.sent = sent;
}"""


def test_a_trainer_that_holds_a_power_is_given_the_workout_s_watts_within_its_range(page: Page):
    errors = _with_bluetooth(page)
    page.evaluate(_TRAINER, [50, 400])
    sent = page.evaluate(
        """async () => {
            const settle = () => new Promise(done => setTimeout(done, 60));
            Trainer.update(10, 4, me, 250); await settle();   // ERG: the step's 250 W
            Trainer.update(10.5, 4, me, 260); await settle(); // within the second: nothing more
            Trainer.update(12, 4, me, 600); await settle();   // more than the trainer holds: its most
            Trainer.update(14, 4, me, null); await settle();  // ERG off: the grade, at once
            return { sent, held: Trainer.held, grade: Trainer.sent };
        }"""
    )
    assert [bytes[:5] for bytes in sent["sent"]] == [
        [0x05, 250, 0],
        [0x05, 400 & 255, 400 >> 8],
        [0x11, 0, 0, 400 & 255, 400 >> 8],
    ], sent
    assert (sent["held"], sent["grade"]) == (None, 4), sent
    assert errors == [], errors


def test_a_trainer_that_holds_no_power_keeps_the_grade(page: Page):
    errors = _with_bluetooth(page)
    page.evaluate(_TRAINER, None)
    sent = page.evaluate(
        "async () => { Trainer.update(10, 4, me, 250); await new Promise(done => setTimeout(done, 60)); return sent; }"
    )
    assert [bytes[:5] for bytes in sent] == [[0x11, 0, 0, 400 & 255, 400 >> 8]], sent
    assert errors == [], errors


@pytest.mark.parametrize("holds", [True, False])
def test_the_trainer_says_whether_it_holds_a_power_and_between_which_watts(page: Page, holds: bool):
    errors = _with_bluetooth(page)
    found = page.evaluate(
        """async holds => {
            // FTMS Fitness Machine Feature: the second field's bit 3 is Power Target Setting
            const feature = new DataView(new ArrayBuffer(8)); feature.setUint32(4, holds ? 8 : 0, true);
            const range = new DataView(new ArrayBuffer(6)); range.setInt16(0, 25, true); range.setInt16(2, 1200, true);
            const point = { addEventListener() {}, async startNotifications() {}, async writeValueWithResponse() {} };
            const quiet = { addEventListener() {}, async startNotifications() {} };
            const characteristics = { 0x2ACC: { async readValue() { return feature; } },
                                      0x2AD8: { async readValue() { return range; } }, 0x2AD9: point };
            const ftms = { async getCharacteristic(uuid) { return characteristics[uuid] || quiet; } };
            const server = { async getPrimaryService(uuid) {
                if (uuid === 0x1826) return ftms; throw new Error('-'); } };
            const gatt = { async connect() { return server; } };
            const trainer = new BLEDev({ name: 'trainer', addEventListener() {}, gatt });
            trainer.command = async () => 1; // control granted at once
            await trainer.connect();
            return trainer.ergRange;
        }""",
        holds,
    )
    assert found == ([25, 1200] if holds else None)
    assert errors == [], errors


def test_a_workout_s_ramp_moves_its_target_and_its_cues_come_on_time(page: Page):
    errors = _ride_alone(page)
    ridden = page.evaluate(
        """() => {
            const cues = []; rideHooks.planCue = text => cues.push([Math.round(Work.t), text]);
            // a minute's ramp from 100 to 200 W, then half a minute at 150 W and 90 rpm
            Work.start([{ min: 1, w: 100, w2: 200 }, { min: 0.5, w: 150, cad: 90 }],
                       [{ at_s: 30, text: 'Halfway up' }, { at_s: 75, text: 'Hold it' }], 'Ramp');
            const targets = {};
            for (let i = 1; i <= 100 * 20; i++) {
                const w = Work.target();
                if (i % 300 === 0) targets[i / 20] = w;
                if (Work.update(0.05, 90, 'power', w)) break; // riding exactly at the target
            }
            const each = key => Work.ss.map(s => Math.round(s[key]));
            return { cues, targets, aimed: each('aimed'), zone: each('zone') };
        }"""
    )
    # read just before each step of the ride: at 59.95 s the ramp is at its top, then 150 W to the end
    assert ridden["targets"] == {"15": 125, "30": 150, "45": 175, "60": 200, "75": 150, "90": 150}, ridden
    assert ridden["cues"] == [[30, "Halfway up"], [75, "Hold it"]], ridden
    assert ridden["zone"] == ridden["aimed"] == [60, 30], ridden
    assert errors == [], errors


# the plan screen's own part of the page, the words and the store, and stand-ins for the rest
_PLAN_SCREEN = """
<style>.hidden{display:none}</style>
<div id="plIcu" class="hidden"><p id="plIcuHint"></p><div id="plIcuList"></div><p id="plIcuInfo"></p></div>
<div id="plOwn"><p>the own plan by gears and cadence</p></div>
"""
_LIST = [
    {"id": 8, "date": "2026-11-20", "name": "Openers", "duration_s": None},
    {"id": 9, "date": "2026-11-21", "name": "Sweet spot", "duration_s": 3600},
]
_WORKOUT = {
    "id": 9,
    "date": "2026-11-21",
    "name": "Sweet spot",
    "duration_s": 3600,
    "ftp_w": 250,
    "steps": [
        {"duration_s": 300, "power_w": 100, "power_end_w": 200, "cadence_rpm": None},
        {"duration_s": 600, "power_w": 225, "power_end_w": 225, "cadence_rpm": 90},
    ],
    "cues": [{"at_s": 300, "text": "Hold it"}],
}


def _plan_screen(page: Page, connected: bool = True, workout_fails: bool = False) -> list[str]:
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_content(_PLAN_SCREEN)
    for name in ("text/ru.js", "text/kk.js", "text/en.js", "js/page.js", "js/i18n.js", "js/helpers.js"):
        page.add_script_tag(path=_ALATAU / name)
    page.evaluate(
        """({ connected, list, workout, fails }) => {
            globalThis.asked = [];
            globalThis.settings = { plan: { steps: [{ f: 1, r: 1, cad: 80, min: 5 }] } }; globalThis.phase = 'menu';
            globalThis.planTotalMin = () => 28; globalThis.renderStartSum = () => {};
            globalThis.saveSettings = () => store.set('settings', settings);
            globalThis.Records = { me: { authenticated: true, intervals_connected: connected } };
            globalThis.Site = { get: async path => {
                asked.push(path);
                if (path.startsWith('/intervals/workouts?')) return list;
                if (fails) throw new Error('intervals.icu answered 503');
                return workout;
            } };
        }""",
        {"connected": connected, "list": _LIST, "workout": _WORKOUT, "fails": workout_fails},
    )
    page.add_script_tag(path=_ALATAU / "js" / "workouts.js")
    page.evaluate("() => loadIcuWorkouts()")
    return errors


def test_the_plan_screen_lists_the_week_from_intervals_icu_and_rides_the_one_picked(page: Page):
    errors = _plan_screen(page)
    options = page.locator("#plIcuList button")
    expect(options).to_have_count(3)
    expect(page.locator("#plIcuHint")).to_have_text(page.evaluate("t('icu.list')"))
    # the own plan comes first and is ridden until a workout is picked
    expect(options.nth(0)).to_have_attribute("aria-pressed", "true")
    expect(options.nth(0).locator("b")).to_have_text(page.evaluate("t('plan.mine')"))
    expect(options.nth(2).locator(".meta")).to_contain_text("1:00:00")
    # the list is asked for from the rider's own today
    assert page.evaluate("asked[0]") == page.evaluate("'/intervals/workouts?oldest=' + localDay(new Date())")
    options.nth(2).click()
    expect(options.nth(2)).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#plOwn")).to_be_hidden()
    said = page.evaluate("t('icu.picked', { name: 'Sweet spot', n: 2, t: '15:00' }) + t('icu.ftp', { w: 250 })")
    expect(page.locator("#plIcuInfo")).to_have_text(said)
    ride = page.evaluate("planToRide()")
    assert ride == {
        "name": "Sweet spot",
        "cues": [{"at_s": 300, "text": "Hold it"}],
        "steps": [{"min": 5, "w": 100, "w2": 200, "cad": None}, {"min": 10, "w": 225, "w2": 225, "cad": 90}],
    }, ride
    assert page.evaluate("planWaits()") is False
    # the settings the page keeps in the browser carry only the picked event's id, not the workout
    assert page.evaluate("settings.planIcu") == 9
    assert errors == [], errors


def test_a_workout_that_did_not_load_says_why_and_holds_the_start(page: Page):
    errors = _plan_screen(page, workout_fails=True)
    page.locator("#plIcuList button").nth(2).click()
    said = page.evaluate("t('icu.pickFailed', { name: 'Sweet spot', msg: 'intervals.icu answered 503' })")
    expect(page.locator("#plIcuInfo")).to_have_text(said)
    assert page.evaluate("planWaits()") is True
    # the own plan is one tap away
    page.locator("#plIcuList button").nth(0).click()
    expect(page.locator("#plOwn")).to_be_visible()
    assert page.evaluate("planWaits()") is False
    assert errors == [], errors


def test_without_intervals_icu_the_plan_screen_is_the_own_plan_alone(page: Page):
    errors = _plan_screen(page, connected=False)
    expect(page.locator("#plIcu")).to_be_hidden()
    expect(page.locator("#plOwn")).to_be_visible()
    assert page.evaluate("asked") == []
    assert page.evaluate("planToRide().name") is None
    assert errors == [], errors


@pytest.mark.django_db(transaction=True)
def test_a_workout_by_power_shows_its_watts_and_cadence_on_the_hud(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        """() => {
            Records.me = { authenticated: true, intervals_connected: true };
            settings.mode = 'plan'; settings.planIcu = 9;
            Icu.plan = { name: 'Sweet spot', ftp: 250, cues: [],
                         steps: [{ min: 1, w: 200, w2: 200, cad: 90 }, { min: 1, w: null, w2: null, cad: null }] };
            startRace();
        }"""
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")
    expect(page.locator("#tVal")).to_have_text("200")
    expect(page.locator("#tUnit")).to_have_text(page.evaluate("t('u.w')"))
    expect(page.locator("#tTitle")).to_have_text(page.evaluate("t('plan.holdPower') + ', 90 ' + t('u.rpm')"))
    expect(page.locator("#plItems li")).to_have_count(2)
    # no trainer that holds a power is connected: no ERG switch to offer
    expect(page.locator("#btnErg")).to_be_hidden()


def test_a_trainer_that_refuses_to_hold_a_power_is_ridden_by_the_grade(page: Page):
    errors = _with_bluetooth(page)
    found = page.evaluate(
        """async () => {
            // it said it holds a power, then answers Set Target Power "Op Code Not Supported" (2)
            const trainer = new BLEDev({ name: 'trainer' }), sent = [];
            trainer.ctrl = true; trainer.roles.add('trainer'); trainer.ergRange = [0, 2000];
            trainer.write = async bytes => {
                sent.push(bytes[0]);
                const result = bytes[0] === 0x05 ? 2 : 1;
                setTimeout(() => trainer.onCtrl(new DataView(new Uint8Array([0x80, bytes[0], result]).buffer)), 5);
            };
            Sensors.devs.push(trainer);
            const settle = () => new Promise(done => setTimeout(done, 60));
            Trainer.update(10, 4, me, 250); await settle();
            Trainer.update(12, 4, me, 250); await settle();
            return { sent, range: trainer.ergRange, grade: Trainer.sent };
        }"""
    )
    # refused once, then no more power asked of it: the route's grade instead
    assert found == {"sent": [0x05, 0x11], "range": None, "grade": 4}, found
    assert errors == [], errors


def _menu_in_kazakh(page: Page, live_server, size) -> None:
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.add_init_script(_FRAMES)
    page.goto(f"{live_server.url}/static/trainer/alatau.html?lang=kk")  # the longest words
    page.evaluate("drawFrame(16)")
    if not page.evaluate("typeof phase !== 'undefined' && phase === 'menu'"):
        pytest.skip("this browser cannot draw 3D, so the page does not start in it")
    page.evaluate(
        """() => {
            Records.me = { authenticated: true, intervals_connected: true };
            Icu.list = [
                { id: 1, date: '2026-11-21', duration_s: 5400,
                  name: 'Sweet spot 3x12 with over-unders and a long cool-down' },
                { id: 2, date: '2026-11-22', name: 'VO2maxIntervalsWithoutAnySpacesInTheNameAtAll', duration_s: 3600 },
            ];
            settings.mode = 'plan'; settings.planIcu = 1;
            Icu.plan = { name: 'Sweet spot', ftp: 250, cues: [],
                         steps: [{ min: 1, w: 200, w2: 200, cad: 90 }, { min: 1, w: 100, w2: 300, cad: 95 }] };
            renderPlanEditor(); renderIcu();
        }"""
    )


@pytest.mark.parametrize("width", [360, 320])
@pytest.mark.django_db(transaction=True)
def test_the_workout_list_fits_a_narrow_phone_in_kazakh(page: Page, live_server, width: int):
    """Long names wrap rather than widen the page, and each workout is a whole button to tap."""
    _menu_in_kazakh(page, live_server, (width, 740))
    fit = page.evaluate(
        """() => ({ page: document.scrollingElement.scrollWidth,
            off: [...document.querySelectorAll('#plIcuList button')].map(b => b.getBoundingClientRect())
                .filter(r => r.height < 44 || r.right > innerWidth).length })"""
    )
    assert fit == {"page": width, "off": 0}, fit


@pytest.mark.parametrize("size", [(360, 740), (320, 640), (844, 390)])
@pytest.mark.django_db(transaction=True)
def test_the_power_target_fits_the_hud_on_a_phone_in_kazakh(page: Page, live_server, size):
    """The longest title a power step shows -- held by ERG, with its cadence -- is not cut off on a phone."""
    _menu_in_kazakh(page, live_server, size)
    page.evaluate("startRace()")
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("() => { Trainer.held = 200; drawFrame(200); }")
    title, panel, width = page.evaluate(
        """() => { const t = document.querySelector('#tTitle');
            return [{ scroll: t.scrollWidth, client: t.clientWidth, right: t.getBoundingClientRect().right },
                    document.querySelector('#target').getBoundingClientRect().right,
                    document.scrollingElement.scrollWidth]; }"""
    )
    assert title["scroll"] <= title["client"] and title["right"] <= panel, (title, panel)
    assert width == size[0], width


@pytest.mark.django_db(transaction=True)
def test_a_workout_without_targets_tells_no_time_on_target(page: Page, live_server):
    """A workout by heart rate comes without power: no "0 % on target" for a rider who was never given one."""
    _trainer_in_its_menu(page, live_server)
    page.evaluate(
        """() => {
            Records.me = { authenticated: true, intervals_connected: true };
            settings.mode = 'plan'; settings.planIcu = 9;
            Icu.plan = { name: 'Zone 2', ftp: null, cues: [], steps: [{ min: 1, w: null, w2: null, cad: null }] };
            startRace();
        }"""
    )
    page.wait_for_function("phase === 'countdown'", polling=100)
    page.evaluate("drawFrame(200)")
    expect(page.locator("#plFoot")).to_have_text(page.evaluate("t('plan.footerStep', { i: 1, n: 1 })"))
    expect(page.locator("#tTitle")).to_have_text(page.evaluate("t('plan.freeHint')"))
