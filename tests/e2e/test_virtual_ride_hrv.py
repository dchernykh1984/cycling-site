"""Write HRV on the virtual ride: the box, the RR intervals read from a strap, and the ride saved with them."""

import json

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_virtual_ride import _trainer_in_its_menu


@pytest.mark.django_db(transaction=True)
def test_the_hrv_box_is_kept_and_the_strap_s_rr_intervals_go_with_the_ride(page: Page, live_server):
    _trainer_in_its_menu(page, live_server)
    expect(page.locator("label:has(#hrvOn)")).to_have_text(page.evaluate("t('bt.hrv')"))
    expect(page.locator("#hrvHint")).to_have_text(page.evaluate("t('bt.hrvHint')"))
    page.check("#hrvOn")
    assert json.loads(page.evaluate("localStorage.getItem('alatau:settings')"))["hrv"] is True
    # a heart rate measurement's RR intervals, in 1/1024 s: after a one-byte pulse; after a two-byte pulse and the
    # energy spent; and none when its flags say there are none
    parsed = page.evaluate(
        """() => [
            [0x10, 72, 0x00, 0x04, 0x33, 0x03],
            [0x19, 72, 0, 5, 0, 0x00, 0x04],
            [0x00, 72],
        ].map(bytes => parseRR(new DataView(new Uint8Array(bytes).buffer)))"""
    )
    assert parsed == [[1000, 800], [1000], []], parsed
    # the ride keeps those a heart beats in, only with the box on
    kept = page.evaluate(
        """() => {
            Sensors.takeRR = () => [800, 100, 900, 3000];
            const on = { rr: [] }; takeRR(on);
            settings.hrv = false; const off = { rr: [] }; takeRR(off); settings.hrv = true;
            return [on.rr, off.rr];
        }"""
    )
    assert kept == [[800, 900], []], kept
    # and the saved ride carries them with its track
    body = page.evaluate(
        """async () => {
            let sent; Records.synced = true; Site.post = async (path, b) => { sent = b; return new Promise(() => {}); };
            me = { track: [[0, 43.24, 76.93, 832, 0, 8, 200, 88, 140], [1, 43.24, 76.93, 832, 8, 8, 200, 88, 141]],
                rr: [812, 805], stats: { maxHR: 141 } };
            Records.push({ route: 'center', time: 2, dist: 0.016 }, []);
            return sent;
        }"""
    )
    assert body["rr"] == [812, 805] and len(body["track"]) == 2, body
