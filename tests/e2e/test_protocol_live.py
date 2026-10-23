"""A live protocol shows the newest results it actually received, and ends only on them."""

import hashlib
import json
import re

import pytest
from django.core.files.base import ContentFile
from django.utils.translation import gettext, override
from playwright.sync_api import Page, Route, expect

from protocols.models import Protocol

POLL_MS = 300
LOAD_TIMEOUT_MS = 1500


@pytest.fixture(autouse=True)
def fast_live_loop(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.PROTOCOL_POLL_INTERVAL_MS = POLL_MS
    settings.PROTOCOL_LOAD_TIMEOUT_MS = LOAD_TIMEOUT_MS


def _body(text: str) -> bytes:
    return f"<html><body><p>{text}</p></body></html>".encode()


def _publish(protocol: Protocol, text: str, *, is_live: bool) -> None:
    """What an upload does to the row: a new file under a new name, its hash, the live flag."""
    content = _body(text)
    protocol.html_file.save("protocol.html", ContentFile(content), save=False)
    protocol.file_hash = hashlib.sha256(content).hexdigest()
    protocol.is_live = is_live
    protocol.save()


def _live_protocol(competition, text: str = "Version A") -> Protocol:
    protocol = Protocol(competition=competition, protocol_type="absolute")
    _publish(protocol, text, is_live=True)
    return protocol


def _open(page: Page, live_server, protocol: Protocol):
    page.goto(f"{live_server.url}/ru/protocols/{protocol.pk}/")
    frame = page.frame_locator("#protocol-frame")
    return frame


def _final_text() -> str:
    with override("ru"):
        return gettext("Final results")


@pytest.mark.django_db(transaction=True)
def test_new_version_published_as_final_is_shown_before_the_final_banner(page: Page, live_server, approved_competition):
    protocol = _live_protocol(approved_competition)
    frame = _open(page, live_server, protocol)
    expect(frame.get_by_text("Version A")).to_be_visible()

    _publish(protocol, "Version B", is_live=False)

    expect(frame.get_by_text("Version B")).to_be_visible(timeout=10_000)
    expect(page.locator("#live-banner")).to_have_text(_final_text())
    expect(page.locator("iframe")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
def test_failed_reload_keeps_the_shown_results_and_tries_again(page: Page, live_server, approved_competition):
    protocol = _live_protocol(approved_competition)
    frame = _open(page, live_server, protocol)
    expect(frame.get_by_text("Version A")).to_be_visible()

    failing = {"on": True}

    def maybe_fail(route: Route):
        if failing["on"]:
            route.fulfill(status=500, body="Server Error")
        else:
            route.continue_()

    page.route(re.compile(r".*/protocols/\d+/html/\?v=.*"), maybe_fail)
    _publish(protocol, "Version B", is_live=False)

    # The final metadata arrived, the content did not: the old results stay, and live goes on.
    expect(page.locator("#live-error")).to_be_visible(timeout=10_000)
    expect(page.frame_locator("#protocol-frame").get_by_text("Version A")).to_be_visible()
    expect(page.locator("#live-banner")).not_to_have_text(_final_text())

    failing["on"] = False
    expect(page.frame_locator("#protocol-frame").get_by_text("Version B")).to_be_visible(timeout=10_000)
    expect(page.locator("#live-banner")).to_have_text(_final_text())
    expect(page.locator("#live-error")).to_be_hidden()


@pytest.mark.django_db(transaction=True)
def test_live_ends_on_the_content_received_not_on_the_hint(page: Page, live_server, approved_competition):
    protocol = _live_protocol(approved_competition)
    frame = _open(page, live_server, protocol)
    expect(frame.get_by_text("Version A")).to_be_visible()

    # The hint says an upload is final, but by the time the content is fetched a newer, still-live
    # upload has replaced it: the page shows the newer one and keeps polling.
    page.route(
        re.compile(r".*/api/protocols/\d+/last_updated/"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"last_updated": "", "file_hash": "older-final", "is_live": False, "shown": "html"}),
        ),
    )
    _publish(protocol, "Version B", is_live=True)

    expect(page.frame_locator("#protocol-frame").get_by_text("Version B")).to_be_visible(timeout=10_000)
    page.wait_for_timeout(3 * POLL_MS + LOAD_TIMEOUT_MS)
    expect(page.locator("#live-banner")).not_to_have_text(_final_text())


@pytest.mark.django_db(transaction=True)
def test_content_in_another_form_reloads_the_page_instead_of_swapping(page: Page, live_server, approved_competition):
    protocol = _live_protocol(approved_competition)
    _open(page, live_server, protocol)
    expect(page.frame_locator("#protocol-frame").get_by_text("Version A")).to_be_visible()
    page.evaluate("window.__beforeReload = true")

    announces_document = (
        "<html><body><p>Version B</p><script>parent.postMessage({type:'protocol-loaded',"
        "hash:'b',is_live:false,shown:'document'},'*');</script></body></html>"
    )
    page.route(
        re.compile(r".*/protocols/\d+/html/\?v=.*"),
        lambda route: route.fulfill(status=200, content_type="text/html", body=announces_document),
    )
    _publish(protocol, "Version B", is_live=False)

    page.wait_for_function("() => window.__beforeReload === undefined", timeout=10_000)


@pytest.mark.django_db(transaction=True)
def test_hiding_and_showing_the_tab_never_runs_two_polls_at_once(page: Page, live_server, approved_competition):
    page.add_init_script(
        """
        (() => {
          let inFlight = 0;
          window.__polls = 0;
          window.__maxInFlight = 0;
          const realFetch = window.fetch;
          window.fetch = function (url, options) {
            if (!String(url).includes("last_updated")) return realFetch(url, options);
            inFlight += 1;
            window.__polls += 1;
            window.__maxInFlight = Math.max(window.__maxInFlight, inFlight);
            return new Promise((resolve) => setTimeout(resolve, 400))
              .then(() => realFetch(url, options))
              .finally(() => { inFlight -= 1; });
          };
          let hidden = false;
          Object.defineProperty(document, "hidden", { get: () => hidden });
          window.__setHidden = (value) => {
            hidden = value;
            document.dispatchEvent(new Event("visibilitychange"));
          };
        })();
        """
    )
    protocol = _live_protocol(approved_competition)
    _open(page, live_server, protocol)
    expect(page.frame_locator("#protocol-frame").get_by_text("Version A")).to_be_visible()

    for _ in range(6):
        page.evaluate("window.__setHidden(true)")
        page.evaluate("window.__setHidden(false)")
    page.wait_for_timeout(1500)

    assert page.evaluate("window.__polls") > 0
    assert page.evaluate("window.__maxInFlight") == 1


@pytest.mark.django_db(transaction=True)
def test_fullscreen_button_has_a_name_and_the_protocol_opens_on_its_own(page: Page, live_server, approved_competition):
    protocol = _live_protocol(approved_competition)
    _open(page, live_server, protocol)
    with override("ru"):
        fullscreen = gettext("Fullscreen")
        separately = gettext("Open the protocol separately")
    expect(page.get_by_role("button", name=fullscreen)).to_be_visible()
    link = page.get_by_role("link", name=separately)
    expect(link).to_have_attribute("href", f"/ru/protocols/{protocol.pk}/html/?v={protocol.file_hash}")
