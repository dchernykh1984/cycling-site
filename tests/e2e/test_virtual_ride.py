"""Record labels render independently of WebGL and external trainer sensors."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from playwright.sync_api import Page, expect


@pytest.mark.parametrize("demo", [False, True])
def test_a_route_record_keeps_its_date_and_demo_label(page: Page, demo: bool):
    source = (Path(settings.BASE_DIR) / "trainer/static/trainer/alatau.html").read_text(encoding="utf-8")
    function = re.search(r"function renderRecords\(\) \{.*?^\}", source, re.DOTALL | re.MULTILINE)
    assert function is not None
    # Exercise the shipped DOM renderer without depending on a GPU, CDN or Bluetooth.
    page.set_content(
        '<div id="recSync"></div><div id="recTotals"></div><div id="recPeaks"></div>'
        '<div id="recRoutes"></div><div id="recHist"></div><button id="btnRecReset"></button>'
    )
    page.evaluate(
        """({render, demo}) => {
            const $ = s => document.querySelector(s);
            const ROUTES = [{id: 'center', name: 'Center'}], PEAKS = [];
            const fmtDate = () => 'DATE', fmtTime = String, fmt1 = String, routeName = String;
            const Records = {synced: false, data: {
                routes: {center: {time: 120, date: 1, attempts: 2, demo}},
                peaks: {}, totals: {rides: 2, dist: 4, gain: 1, time: 240}, history: []
            }};
            eval(render + '; renderRecords();');
        }""",
        {"render": function.group(), "demo": demo},
    )
    label = "DATE" + (", \u0434\u0435\u043c\u043e" if demo else "") + ", \u043f\u043e\u043f\u044b\u0442\u043e\u043a: 2"
    expect(page.locator("#recRoutes small")).to_have_text(label)
