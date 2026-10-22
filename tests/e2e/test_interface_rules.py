"""The interface rules (.claude/skills/interface/SKILL.md), measured on the calendar, the list and the map.

The three tabs are one page to a reader: switching between them must move nothing, every control
must be big enough for a finger, say what it does, fit its words in all three languages and stay
readable. Runs in the skin the suite runs in (E2E_SKIN; light by default), so e2e.yml checks every
skin; a phone and a desktop width are set here, so each browser job checks both.

KNOWN lists what already broke a rule when the rule came in, and only so far: a new break fails.
A layout break is the site's and is allowed in every skin; a colour break -- text, a border, a
selected state -- only in light and dark.
"""

import re

import pytest
from django.conf import settings
from playwright.sync_api import Page, ViewportSize, expect

from tests.e2e.conftest import AROUND_UPCOMING
from tests.e2e.contrast import drawn, is_large, legibility, ratio

TABS = {"calendar": "/calendar/", "list": "/calendar/list/", "map": "/calendar/map/"}
VIEWPORTS: dict[str, ViewportSize] = {"phone": {"width": 360, "height": 780}, "desktop": {"width": 1280, "height": 900}}
# The narrowest width WCAG asks a page to reflow at (1.4.10): the site is designed for 360px and up,
# and at 320px only nothing may be cut off or spill over -- the screen's edge or a frame.
NARROW: ViewportSize = {"width": 320, "height": 700}
LANGUAGES = ("ru", "kk", "en")
# What the three tabs share above their content: the title row with the switcher, and -- where a
# page has them -- the period row and the chips of the filters in force.
HEADER = "main .row:has(#view-link-calendar), #period-nav, #filter-chips"
CONTROLS = ":is(a, button, select, input):visible"
# Apple's and WCAG 2.5.5's smallest target for a finger.
TAP = 44
STATES = ("rest", "hover", "focus")
# Breaks that come from a skin's colours rather than from the site's layout.
COLOURS = ("contrast/", "border/", "selected/")

# One name per control that does not change with the language or the active tab: its id, its own
# data attributes (with the value only when it is a code, not a translated phrase), a class of its
# own, its link without the language prefix, or its tag and text.
_DESCRIBE = """
(el) => {
  const own = [...el.attributes].filter(a => a.name.startsWith('data-') && !a.name.startsWith('data-bs-'));
  // Bootstrap's own classes and the state ones say nothing about which control this is.
  const utility = new RegExp('^(active|show|collapsed|small'
    + '|(btn|d|align|justify|flex|gap|text|w|h|fw|rounded|border)(-.*)?|[mp][trblxyse]?-.*)$');
  const mine = [...el.classList].filter(c => !utility.test(c));
  const href = el.getAttribute('href');
  const key = el.id ? '#' + el.id
    : own.length ? '[' + own.map(a => /^[a-z0-9_-]{1,24}$/i.test(a.value) ? a.name + '=' + a.value : a.name)
                                .join('][') + ']'
    : mine.length ? el.tagName.toLowerCase() + '.' + mine[0]
    : href ? 'a[href=' + href.replace(/^\\/(ru|kk|en)\\//, '/') + ']'
    : el.tagName.toLowerCase() + ':' + el.textContent.trim();
  const r = el.getBoundingClientRect();
  const box = [r.x, r.y, r.width, r.height].map(v => Math.round(v * 10) / 10);
  return {key, box, width: r.width, height: r.height, scroll: el.scrollWidth, client: el.clientWidth,
          // The slot the period row leaves for one page's own controls (the calendar's Grid/List).
          own_slot: !!el.closest('#period-extra'),
          // A title is not a name: a phone never shows it and screen readers do not reliably read it.
          name: (el.getAttribute('aria-label') || el.innerText || '').trim()};
}
"""

KNOWN: set[str] = set()


def _breaks(found):
    """The breaks that are not KNOWN for this skin.

    A layout break is the site's own and is allowed in every skin; a contrast break is the skin's
    colours, allowed only in light and dark -- a designer's skin gets no allowance for its own.
    """
    maintainers = settings.DEFAULT_SKIN in ("light", "dark")
    return [item for item in found if item not in KNOWN or (item.startswith(COLOURS) and not maintainers)]


def _open(page: Page, live_server, viewport, lang, tab, query=""):
    page.set_viewport_size(NARROW if viewport == "narrow" else VIEWPORTS[viewport])
    page.goto(f"{live_server.url}/{lang}{TABS[tab]}{query}")
    expect(page.locator("#view-link-calendar")).to_be_visible()
    if tab == "calendar":
        # FullCalendar draws after the page loads; measured before that, the page was briefly wider.
        expect(page.locator(".fc-view")).to_be_visible()
    page.wait_for_load_state("networkidle")


def _controls(page: Page):
    """Every visible control in the shared header, described."""
    return [control.evaluate(_DESCRIBE) for control in page.locator(HEADER).locator(CONTROLS).all()]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", [*VIEWPORTS, "narrow"])
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_no_tab_scrolls_sideways(page: Page, live_server, viewport, lang, tab):
    _open(page, live_server, viewport, lang, tab)
    wide, screen = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    found = [f"sideways/{viewport}/{lang}/{tab}"] if wide > screen else []
    assert not _breaks(found), f"the page is {wide}px wide in a {screen}px screen"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("lang", LANGUAGES)
def test_switching_tabs_moves_none_of_the_controls(page: Page, live_server, viewport, lang):
    """Each control of the header is drawn by one partial in the same place on all three tabs.

    A page's own controls in the period row's slot (#period-extra) are its own by design.
    """
    boxes = {}
    for tab in TABS:
        _open(page, live_server, viewport, lang, tab)
        boxes[tab] = {control["key"]: control["box"] for control in _controls(page) if not control["own_slot"]}
    found, details = [], []
    for key in sorted(set().union(*boxes.values())):
        where = {tab: boxes[tab].get(key) for tab in TABS}
        if len({str(box) for box in where.values()}) > 1:
            found.append(f"moves/{viewport}/{lang}/{key}")
            details.append(f"{key}: {where}")
    assert not _breaks(found), "\n".join(details)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_every_control_is_big_enough_to_tap_on_a_phone(page: Page, live_server, lang, tab):
    _open(page, live_server, "phone", lang, tab)
    small = [c for c in _controls(page) if c["width"] < TAP or c["height"] < TAP]
    found = [f"tap/{lang}/{tab}/{c['key']}" for c in small]
    assert not _breaks(found), [f"{c['key']}: {c['width']:.0f}x{c['height']:.0f}" for c in small]


# Where a control's words sit inside its frame: how many lines, how far from the frame, how far apart.
# A control with neither a frame nor a fill (a tappable month in the period label) has no frame to
# keep clear of, and is measured for its lines only.
_LABEL = """
(el) => {
  const r = el.getBoundingClientRect(), s = getComputedStyle(el);
  // The words only: an icon beside them sits at its own height and is not a line of text.
  const rects = [];
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walk.nextNode(); node; node = walk.nextNode()) {
    if (!node.textContent.trim()) continue;
    const range = document.createRange(); range.selectNodeContents(node);
    rects.push(...[...range.getClientRects()].filter(q => q.width > 1 && q.height > 1));
  }
  if (!rects.length) return null;
  const lines = new Set(rects.map(q => Math.round(q.top))).size;
  const bw = parseFloat(s.borderLeftWidth) || 0, bt = parseFloat(s.borderTopWidth) || 0;
  const left = Math.min(...rects.map(q => q.left)), right = Math.max(...rects.map(q => q.right));
  const top = Math.min(...rects.map(q => q.top)), bottom = Math.max(...rects.map(q => q.bottom));
  const clear = (c) => c === 'transparent' || /,\\s*0\\)$/.test(c);
  // A segment of a group (the period kinds) is framed by the group's border, not its own.
  const group = el.closest('[role="group"]');
  const framed = (bw > 0 && s.borderLeftStyle !== 'none') || !clear(s.backgroundColor)
    || (!!group && parseFloat(getComputedStyle(group).borderTopWidth) > 0);
  return {lines, framed, side: Math.min(left - r.left - bw, r.right - bw - right),
          end: Math.min(top - r.top - bt, r.bottom - bt - bottom),
          spacing: parseFloat(s.lineHeight) / parseFloat(s.fontSize)};
}
"""
SIDE, END, LINES, SPACING = 8, 4, 2, 1.2


def _label_faults(label, narrow):
    """What is wrong with where a label's words sit; at 320px only what is cut off or spills over."""
    if narrow:
        return ["over the frame"] if label["framed"] and min(label["side"], label["end"]) < -0.5 else []
    faults = []
    if label["lines"] > LINES:
        faults.append(f"{label['lines']} lines")
    if label["lines"] > 1 and label["spacing"] < SPACING - 0.01:
        faults.append(f"line spacing {label['spacing']:.2f}")
    if label["framed"] and label["side"] < SIDE - 0.5:
        faults.append(f"{label['side']:.0f}px from the frame at the side")
    if label["framed"] and label["end"] < END - 0.5:
        faults.append(f"{label['end']:.0f}px from the frame above or below")
    return faults


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", [*VIEWPORTS, "narrow"])
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_every_label_fits_its_control(page: Page, live_server, viewport, lang, tab):
    """Words stay inside their frame with room around them, in all three languages, from 360px up.

    Kazakh is usually the longest. At most two lines, spaced at least 1.2 apart; at least 8px from the
    frame at the sides and 4px above and below -- a word cut off, spilling out or touching the frame
    reads as a broken button. At 320px only what is cut off or spills over counts.
    """
    _open(page, live_server, viewport, lang, tab)
    found, details = [], []
    for control in page.locator(HEADER).locator(CONTROLS).all():
        label = control.evaluate(_LABEL)
        if label is None:
            continue
        key, name, scroll, client = (control.evaluate(_DESCRIBE)[k] for k in ("key", "name", "scroll", "client"))
        faults = [f"{scroll}px in {client}px"] if scroll > client else []
        faults += _label_faults(label, viewport == "narrow")
        if faults:
            found.append(f"fits/{viewport}/{lang}/{tab}/{key}")
            details.append(f"{key} ({name!r}): " + ", ".join(faults))
    assert not _breaks(found), "\n".join(details)


# The top of each button in each group of the header; a group in one row has one top.
_ROWS = """
() => [...document.querySelectorAll('#period-nav [role="group"], main .row:has(#view-link-calendar) [role="group"]')]
  .filter(g => g.offsetParent)
  .map(g => ({name: g.getAttribute('aria-label') || g.className,
              tops: [...new Set([...g.children].filter(c => c.offsetParent)
                                 .map(c => Math.round(c.getBoundingClientRect().top)))]}))
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_a_button_group_stays_in_one_row(page: Page, live_server, viewport, lang, tab):
    """The period kinds and the view switch are read as one row; folded into two, they are a grid."""
    _open(page, live_server, viewport, lang, tab)
    folded = [group for group in page.evaluate(_ROWS) if len(group["tops"]) > 1]
    found = [f"row/{viewport}/{lang}/{tab}/{group['name']}" for group in folded]
    assert not _breaks(found), [f"{group['name']}: {len(group['tops'])} rows" for group in folded]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("tab", TABS)
def test_every_control_says_what_it_does(page: Page, live_server, viewport, tab):
    """An arrow or an icon is never alone: it carries words a screen reader and a tooltip can use."""
    _open(page, live_server, viewport, "ru", tab)
    found = [f"name/{viewport}/{tab}/{c['key']}" for c in _controls(page) if not re.search(r"\w{2}", c["name"])]
    assert not _breaks(found), found


def _in_state(page: Page, control, state):
    """Put a control at rest, under the pointer or in focus, and wait for its fade to finish."""
    page.mouse.move(0, 0)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    if state == "hover":
        control.hover()
    elif state == "focus":
        control.focus()
    # A colour read mid-fade is neither state's.
    control.evaluate("el => Promise.all(el.getAnimations().map(a => a.finished))")


_BORDER = (
    "el => { const s = getComputedStyle(el);"
    " return [parseFloat(s.borderTopWidth), s.borderTopStyle, s.borderTopColor]; }"
)


def _frame(control):
    """The colour a control's border is drawn in, or None when it draws no border."""
    width, style, colour = control.evaluate(_BORDER)
    return drawn(control, f"colour:{colour}") if width > 0 and style != "none" else None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("tab", TABS)
def test_the_header_is_readable_in_this_skin(page: Page, live_server, viewport, tab):
    """The header's controls at rest, under the pointer and in focus, as test_skin_contrast.py measures."""
    _open(page, live_server, viewport, "ru", tab)
    skin = settings.DEFAULT_SKIN
    found, details = [], []
    for control in page.locator(HEADER).locator(CONTROLS).all():
        if not control.is_enabled():
            continue
        key = control.evaluate(_DESCRIBE)["key"]
        for state in STATES:
            _in_state(page, control, state)
            floor = 3 if is_large(control) else 4.5
            value = legibility(control)
            if value < floor:
                found.append(f"contrast/{skin}/{viewport}/{tab}/{key}/{state}")
                details.append(f"{key} ({state}): {value:.2f} < {floor}")
    assert not _breaks(found), f"in the {skin} skin: " + "; ".join(details)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("tab", TABS)
def test_every_border_can_be_seen(page: Page, live_server, viewport, tab):
    """An outline button's border is all that says it is a button: 3:1 against what surrounds it.

    A border drawn in the colour around it is no frame at all and is left out here; when it belongs
    to a selected control, test_what_is_selected_can_be_seen catches it.
    """
    _open(page, live_server, viewport, "ru", tab)
    skin = settings.DEFAULT_SKIN
    found, details = [], []
    page.mouse.move(0, 0)
    for control in page.locator(HEADER).locator(CONTROLS).all():
        frame = _frame(control)
        if frame is None:
            continue
        value = ratio(frame, drawn(control, "fill-beneath"))
        if 1.1 <= value < 3:
            key = control.evaluate(_DESCRIBE)["key"]
            found.append(f"border/{skin}/{viewport}/{tab}/{key}")
            details.append(f"{key}: {value:.2f} < 3")
    assert not _breaks(found), f"in the {skin} skin: " + "; ".join(details)


# Marks one unselected neighbour of a selected control -- same parent, same tag -- to compare with.
_PEER = """
(el) => {
  const on = (e) => e.matches('[aria-current="page"], [aria-pressed="true"], .active');
  const peer = [...el.parentElement.children].find(e => e !== el && e.tagName === el.tagName && !on(e));
  document.querySelectorAll('[data-peer-probe]').forEach(e => e.removeAttribute('data-peer-probe'));
  if (peer) peer.setAttribute('data-peer-probe', '');
  return !!peer;
}
"""
_TOLD = "el => el.matches('[aria-current], [aria-pressed=true]')"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("tab", TABS)
def test_what_is_selected_can_be_seen(page: Page, live_server, viewport, tab):
    """The tab on screen and the period kind stand out from their neighbours by 3:1, fill or frame.

    A heavier word alone does not count, and a screen reader is told too (aria-current, aria-pressed).
    """
    _open(page, live_server, viewport, "ru", tab)
    skin = settings.DEFAULT_SKIN
    found, details = [], []
    page.mouse.move(0, 0)
    selected = page.locator(HEADER).locator(":is([aria-current='page'], [aria-pressed='true'], .active):visible")
    for control in selected.all():
        key = control.evaluate(_DESCRIBE)["key"]
        if not control.evaluate(_TOLD):
            found.append(f"selected-aria/{viewport}/{tab}/{key}")
            details.append(f"{key}: selected only by its look")
        if not control.evaluate(_PEER):
            continue
        peer = page.locator("[data-peer-probe]")
        fill = ratio(drawn(control, "fill"), drawn(peer, "fill"))
        own, theirs = _frame(control), _frame(peer)
        frame = ratio(own or drawn(control, "fill"), theirs or drawn(peer, "fill"))
        if max(fill, frame) < 3:
            found.append(f"selected/{skin}/{viewport}/{tab}/{key}")
            details.append(f"{key}: fill {fill:.2f}, frame {frame:.2f} against its neighbour, < 3")
    assert not _breaks(found), f"in the {skin} skin: " + "; ".join(details)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("tab", TABS)
def test_the_active_tab_keeps_the_border_of_the_others(page: Page, live_server, viewport, tab):
    """The skin draws btn-secondary without a border: an active tab drawn with it shrank and shifted."""
    _open(page, live_server, viewport, "ru", tab)
    borders = page.locator("[id^='view-link-']").evaluate_all(
        "links => links.map(a => { const s = getComputedStyle(a);"
        " return [s.borderTopWidth, s.borderBottomWidth, s.borderTopStyle].join(' '); })"
    )
    found = [f"border/{viewport}/{tab}"] if len(set(borders)) > 1 else []
    assert not _breaks(found), borders


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tab", TABS)
def test_the_period_is_named_in_words(page: Page, live_server, tab):
    """A reader sees which days are on screen without decoding two date fields."""
    _open(page, live_server, "phone", "ru", tab)
    label = page.locator("#period-label")
    words = label.inner_text() if label.count() else ""
    found = [] if re.search(r"[^\W\d_]{3}", words) else [f"period/{tab}"]
    assert not _breaks(found), f"the period label reads {words!r}"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("tab", TABS)
def test_a_hint_takes_one_line(page: Page, live_server, viewport, tab):
    """A hint under a control is read at a glance; two lines push the content down on every tab."""
    _open(page, live_server, viewport, "kk", tab)
    found = []
    for hint in page.locator(".period-hint:visible").all():
        lines = hint.evaluate("el => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)")
        if round(lines) > 1:
            found.append(f"hint/{viewport}/{tab}")
    assert not _breaks(found), found


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tab", TABS)
def test_the_period_and_the_filters_travel_to_the_other_tabs(page: Page, live_server, race_event_type, tab):
    """A reader who narrowed the dates and the type on one tab finds them narrowed on the next."""
    _open(page, live_server, "desktop", "ru", tab, f"?{AROUND_UPCOMING}&event_type={race_event_type.pk}")
    wanted = dict(pair.split("=") for pair in AROUND_UPCOMING.split("&")) | {"event_type": str(race_event_type.pk)}
    found, details = [], []
    for other in TABS:
        if other == tab:
            continue
        href = page.locator(f"#view-link-{other}").get_attribute("href") or ""
        missing = [name for name, value in wanted.items() if f"{name}={value}" not in href]
        if missing:
            found.append(f"travel/{tab}/{other}/{','.join(missing)}")
            details.append(f"{tab} -> {other} drops {missing}: {href}")
    assert not _breaks(found), "\n".join(details)
