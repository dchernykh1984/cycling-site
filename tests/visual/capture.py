"""Screenshots of the site, the same set from any running copy of it (run.py drives this).

Each case is one page, optionally brought into a state first: a picker open, a button hovered, the
page scrolled under the sticky bar. Before the shot the page is checked for the content it is meant
to show, so two empty calendars never pass for two identical ones.
"""

import json
import pathlib

from playwright.sync_api import Page, expect, sync_playwright

THEMES = ("light", "dark")
DEVICES = {
    "desktop": ("chromium", {"viewport": {"width": 1280, "height": 800}}),
    "pixel7": ("chromium", "Pixel 7"),
    "iphone15": ("webkit", "iPhone 15"),
}
# Painted over on both sides before comparing: the map tiles come from the network and change on
# their own; Wagtail's floating admin button is Wagtail's, not a theme's, and its icon's edge has
# rendered a few pixels apart on WebKit. "host >>> inner" looks inside the host's shadow root.
ALWAYS_MASKED = (".leaflet-tile-pane", "wagtail-userbar >>> .w-userbar")
# Changes this branch makes on purpose, kept as narrow as the change. shortcut: the list is edited
# by hand, empty it once the change has landed on main.
ALLOWED_CHANGES = (
    # The profile's theme row: the switch said "Light" in English, the list names the skin.
    ".card-body:has(> button[onclick='toggleTheme()'])",
    ".card-body:has(> .skin-select)",
)


# A guest who has never picked a theme: no cookie, nothing in the browser's storage.
FIRST_VISIT = "first-visit"


def _wait_for_text(*texts):
    def check(page: Page):
        for text in texts:
            expect(page.get_by_text(text, exact=False).first).to_be_visible()

    return check


def _month_has_events(page: Page):
    expect(page.locator(".fc-event").first).to_be_visible()


def _map_has_markers(page: Page):
    expect(page.locator(".leaflet-marker-icon").first).to_be_visible()


def _open_datepicker(page: Page):
    page.wait_for_function("() => !!document.querySelector('input.js-date-filter')._flatpickr")
    page.locator("input.js-date-filter").first.click()
    expect(page.locator(".flatpickr-calendar.open")).to_be_visible()


def _hover_picked_day(page: Page):
    _open_datepicker(page)
    page.locator(".flatpickr-calendar.open .flatpickr-day.selected").first.hover()


def _open_type_filter(page: Page):
    page.locator("#et-btn-1").click()
    expect(page.locator("#et-menu-1")).to_be_visible()


def _hover_nav_link(page: Page):
    page.locator("nav .nav-link").first.hover()


def _keyboard_focus(page: Page):
    for _ in range(4):
        page.keyboard.press("Tab")


def _check_first_box(page: Page):
    page.locator("form input[type='checkbox']:not([disabled]):visible").first.check()


def _scroll_under_sticky_bar(page: Page):
    # Instant: Bootstrap scrolls smoothly, and a shot taken mid-glide lands anywhere.
    page.evaluate("window.scrollTo({top: 700, behavior: 'instant'})")
    page.wait_for_function("() => window.scrollY > 0")
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def _scroll_under_category_band(page: Page):
    """Scroll into the second category, whose band should then stick under the navbar."""
    band = page.locator(".participant-category").nth(1)
    expect(band).to_be_visible()
    page.evaluate(
        "el => window.scrollTo({top: el.getBoundingClientRect().top + scrollY + 150, behavior: 'instant'})",
        band.element_handle(),
    )
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    nav_bottom = page.evaluate("document.querySelector('nav.navbar').getBoundingClientRect().bottom")
    band_top = band.evaluate("el => el.getBoundingClientRect().top")
    assert abs(band_top - nav_bottom) < 2, f"the band is at {band_top}, the navbar ends at {nav_bottom}"


def _open_phone_menu(page: Page):
    page.locator(".navbar-toggler").click()
    page.locator(".navbar-collapse.show").wait_for(state="visible")


def cases(pages):
    upcoming, finished = pages["upcoming"], pages["finished"]
    # (name, path, visitor, check before the shot, state, devices or None for all, full page)
    return [
        ("home", "/ru/", None, None, None, None, True),
        ("month", "/ru/calendar/", None, _month_has_events, None, None, True),
        ("list", "/ru/calendar/list/", None, _wait_for_text("Gran Fondo Alatau"), None, None, True),
        ("list-empty", "/ru/calendar/list/?date_from=2001-01-01&date_to=2001-01-02", None, None, None, None, True),
        ("map", "/ru/calendar/map/", None, _map_has_markers, None, None, True),
        ("event", f"/ru/calendar/{upcoming}/", None, _wait_for_text("Gran Fondo Alatau"), None, None, True),
        ("event-results", f"/ru/calendar/{finished}/", None, _wait_for_text("Tien Shan Trail"), None, None, True),
        (
            "participants",
            f"/ru/competitions/{upcoming}/participants/",
            None,
            _wait_for_text("Sadykova"),
            None,
            None,
            True,
        ),
        ("news", "/ru/news/", None, _wait_for_text("Season news 1"), None, None, True),
        ("news-article", pages["news"], None, _wait_for_text("Season news"), None, None, True),
        ("guide", pages["guide"], None, _wait_for_text("How to pick a first race"), None, None, True),
        ("first-visit", "/ru/calendar/list/", FIRST_VISIT, _wait_for_text("Gran Fondo Alatau"), None, None, True),
        ("search", "/ru/search/?q=Alatau", None, None, None, None, True),
        ("login", "/ru/accounts/login/", None, None, None, None, True),
        ("signup", "/ru/accounts/signup/", None, None, None, None, True),
        ("privacy", "/ru/privacy/", None, None, None, None, True),
        ("not-found", "/ru/no-such-page/", None, None, None, None, True),
        ("profile", "/ru/accounts/profile/", "member", None, None, None, True),
        ("profile-edit", "/ru/accounts/profile/edit/", "member", None, None, None, True),
        ("register", f"/ru/competitions/{upcoming}/register/", "member", None, None, None, True),
        ("submit", "/ru/calendar/submit/", "member", None, None, None, True),
        ("profile-edit-checked", "/ru/accounts/profile/edit/", "member", None, _check_first_box, ("desktop",), True),
        ("moderation", "/ru/calendar/moderate/", "admin", _wait_for_text("Pending Race"), None, None, True),
        ("event-as-admin", f"/ru/calendar/{upcoming}/", "admin", None, None, None, True),
        ("location-edit", f"/ru/locations/{pages['venue']}/edit/", "admin", None, None, None, True),
        ("list-datepicker", "/ru/calendar/list/", None, None, _open_datepicker, ("desktop",), True),
        ("list-datepicker-hover", "/ru/calendar/list/", None, None, _hover_picked_day, ("desktop",), True),
        ("list-type-filter", "/ru/calendar/list/", None, None, _open_type_filter, ("desktop",), True),
        ("hover-nav", "/ru/calendar/list/", None, None, _hover_nav_link, ("desktop",), False),
        ("keyboard-focus", "/ru/calendar/list/", None, None, _keyboard_focus, ("desktop",), False),
        ("sticky-navbar", "/ru/calendar/list/", None, None, _scroll_under_sticky_bar, None, False),
        (
            "sticky-category",
            f"/ru/competitions/{upcoming}/participants/",
            None,
            None,
            _scroll_under_category_band,
            # The band sticks only in the phone layout (cycling_site.css, below the md breakpoint).
            ("pixel7", "iphone15"),
            False,
        ),
        ("phone-menu", "/ru/", None, None, _open_phone_menu, ("pixel7", "iphone15"), False),
    ]


OVERFLOWS = "document.documentElement.scrollWidth > document.documentElement.clientWidth"


def _rects(page: Page, selectors):
    return page.evaluate(
        """sels => sels.flatMap(s => {
            const [host, inner] = s.split(' >>> ');
            if (!inner) return [...document.querySelectorAll(s)];
            return [...document.querySelectorAll(host)]
                .flatMap(h => h.shadowRoot ? [...h.shadowRoot.querySelectorAll(inner)] : []);
        }).map(el => {
            const r = el.getBoundingClientRect();
            return [r.left + scrollX, r.top + scrollY, r.right + scrollX, r.bottom + scrollY];
        }).filter(r => r[2] > r[0] && r[3] > r[1])""",
        list(selectors),
    )


def _browser(playwright, device):
    engine, options = DEVICES[device]
    if isinstance(options, str):
        options = playwright.devices[options]
    return getattr(playwright, engine).launch(), options


def _open(browser, options, base_url, data, now, theme, visitor, path) -> Page:
    """A page as this visitor sees it in this theme, in a context of its own.

    A fresh context per shot: cookies could be cleared between shots, but the browser's storage
    could not, and a first visit would inherit the theme an earlier shot stored there.
    """
    host = base_url.split("//")[1].split(":")[0]
    context = browser.new_context(**options, timezone_id="Asia/Almaty", locale="ru-RU", base_url=base_url)
    # As in the e2e suite: two servers and a browser share a small CI runner.
    context.set_default_timeout(60_000)
    context.set_default_navigation_timeout(60_000)
    cookies = [{"name": "django_language", "value": "ru", "domain": host, "path": "/"}]
    if visitor != FIRST_VISIT:
        cookies.append({"name": "skin", "value": theme, "domain": host, "path": "/"})
    if visitor in ("member", "admin"):
        session = data["sessions"][f"{visitor}_{theme}"]
        cookies.append({"name": "sessionid", "value": session, "domain": host, "path": "/"})
    context.add_cookies(cookies)
    page = context.new_page()
    page.clock.set_fixed_time(now)
    if visitor != FIRST_VISIT:
        # The guest's choice as the site before skins kept it; the one after reads the cookie.
        page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.goto(path, wait_until="networkidle")
    page.evaluate("document.fonts.ready.then(() => true)")
    if visitor == FIRST_VISIT:
        stored = page.evaluate("[localStorage.getItem('theme'), document.cookie.includes('skin=')]")
        assert stored == [None, False], f"a first visit found a stored choice: {stored}"
    return page


def _shots(data, devices, only, wanted):
    """(device, theme, case) for every screenshot asked for."""
    for device in devices:
        for theme in THEMES:
            for case in cases(data["pages"]):
                name, visitor, on_devices = case[0], case[2], case[5]
                # A first-time guest has chosen nothing, so is the same in both themes.
                skipped = (
                    (on_devices and device not in on_devices)
                    or (only and name not in only)
                    or (wanted is not None and f"{device}/{theme}/{name}.png" not in wanted)
                    or (visitor == FIRST_VISIT and theme != THEMES[0])
                )
                if not skipped:
                    yield device, theme, case


def capture(base_url, data, out_dir, now, devices=tuple(DEVICES), only=(), wanted=None):
    """Take every shot into out_dir/<device>/<theme>/<case>.png; return what compare.py needs."""
    meta = {}
    browsers = {}
    with sync_playwright() as playwright:
        for device, theme, (name, path, visitor, check, state, _, full_page) in _shots(data, devices, only, wanted):
            if device not in browsers:
                browsers[device] = _browser(playwright, device)
            page = _open(*browsers[device], base_url, data, now, theme, visitor, path)
            try:
                if check:
                    check(page)
                if state:
                    state(page)
            except AssertionError as error:
                raise AssertionError(f"{device}/{theme}/{name}: {error}") from None
            target = pathlib.Path(out_dir, device, theme, f"{name}.png")
            target.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=target, full_page=full_page, animations="disabled", caret="hide")
            meta[str(target.relative_to(out_dir))] = {
                "masked": _rects(page, ALWAYS_MASKED + ALLOWED_CHANGES),
                "offset": [0, 0] if full_page else page.evaluate("[scrollX, scrollY]"),
                "overflows": page.evaluate(OVERFLOWS),
                # Masks are in CSS pixels; a phone's screenshot has two or three image pixels to each.
                "scale": page.evaluate("devicePixelRatio"),
            }
            page.context.close()
        for browser, _ in browsers.values():
            browser.close()
    pathlib.Path(out_dir, "meta.json").write_text(json.dumps(meta, indent=1))
    return meta
