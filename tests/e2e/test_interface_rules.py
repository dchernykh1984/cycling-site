"""The interface rules (.claude/skills/interface/SKILL.md), measured on the calendar, the list and the map.

The three tabs are one page to a reader: switching between them must move nothing, every control
must be big enough for a finger, say what it does, fit its words in all three languages and stay
readable. Runs in the skin the suite runs in (E2E_SKIN; light by default), so e2e.yml checks every
skin. The widths are set here: a phone (360px) and a desktop (1280px) get every rule; the narrowest
phone (320px) and two tablets (768 and 1024px) only what scrolls sideways, is cut off or breaks.

KNOWN lists what already broke a rule when the rule came in, and only so far: a new break fails.
Each entry names its skin ("light|tap/phone/ru/list/#filter-toggle"). A colour break -- text, an
icon, a boundary, a selection -- is allowed for light and dark only, whatever KNOWN says.
"""

import datetime
import re

import pytest
from django.conf import settings
from playwright.sync_api import Page, ViewportSize, expect

from calendar_app.models import Competition
from tests.e2e.conftest import AROUND_UPCOMING
from tests.e2e.contrast import drawn, is_large, legibility, ratio

TABS = {"calendar": "/calendar/", "list": "/calendar/list/", "map": "/calendar/map/"}
VIEWPORTS: dict[str, ViewportSize] = {"phone": {"width": 360, "height": 780}, "desktop": {"width": 1280, "height": 900}}
# The narrowest width WCAG asks a page to reflow at (1.4.10): the site is designed for 360px and up,
# and at 320px only nothing may be cut off or spill over -- the screen's edge or a frame.
NARROW: ViewportSize = {"width": 320, "height": 700}
# Tablets are not a focus: held upright they get the phone layout, on their side the desktop one.
TABLETS: dict[str, ViewportSize] = {
    "tablet-upright": {"width": 768, "height": 1024},
    "tablet-flat": {"width": 1024, "height": 768},
}
# The widths where only what scrolls sideways, is cut off or breaks into letters is checked.
MINIMAL = ("narrow", *TABLETS)
SIZES: dict[str, ViewportSize] = {**VIEWPORTS, "narrow": NARROW, **TABLETS}
LANGUAGES = ("ru", "kk", "en")
# What the three tabs share above their content: the title row with the switcher, and -- where a
# page has them -- the period row and the chips of the filters in force.
HEADER = "main .row:has(#view-link-calendar), #period-nav, #filter-chips"
CONTROLS = ":is(a, button, select, input):visible"
# The smallest area a tap or a click must reach: Apple's and WCAG 2.5.5's for a finger, WCAG 2.5.8's
# for a mouse.
TAP = {"phone": 44, "desktop": 24}
# The focus ring and the Tab key are left out for now (the skill's principle 11).
STATES = ("rest", "hover")
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

# What broke a rule when the rule came in, by cause. Each entry names its skin, and the set only
# shrinks: a fixed break is dropped here, a new one fails. The orange skin carries its own templates
# and breaks none of these.
KNOWN: set[str] = set()


def _breaks(found):
    """The breaks that are not KNOWN for this skin.

    An entry holds for the skin it names. A colour break is allowed only in light and dark, the
    maintainer's skins -- a designer's skin gets no allowance for its own colours.
    """
    skin = settings.DEFAULT_SKIN
    maintainers = skin in ("light", "dark")
    return [item for item in found if f"{skin}|{item}" not in KNOWN or (item.startswith(COLOURS) and not maintainers)]


def _open(page: Page, live_server, viewport, lang, tab, query=""):
    page.set_viewport_size(SIZES[viewport])
    page.goto(f"{live_server.url}/{lang}{TABS[tab]}{query}")
    expect(page.locator("#view-link-calendar")).to_be_visible()
    if tab == "calendar":
        # FullCalendar draws after the page loads; measured before that, the page was briefly wider.
        expect(page.locator(".fc-view")).to_be_visible()
    page.wait_for_load_state("networkidle")
    # A skin's font arrives with font-display: swap; a label measured before it has the fallback's width.
    page.evaluate("() => document.fonts.ready")


def _controls(page: Page):
    """Every visible control in the shared header, described."""
    return [control.evaluate(_DESCRIBE) for control in page.locator(HEADER).locator(CONTROLS).all()]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", [*VIEWPORTS, *MINIMAL])
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


# How far a tap reaches: from the control's centre outwards, as long as the point still lands on it
# (an invisible zone around a slim control counts; a neighbour's zone over it does not).
_REACH = """
(el) => {
  const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const own = (px, py) => { const t = document.elementFromPoint(px, py); return !!t && (t === el || el.contains(t)); };
  const out = (dx, dy) => { let n = 0; while (n < 40 && own(x + dx * (n + 1), y + dy * (n + 1))) n += 1; return n; };
  return [out(-1, 0) + out(1, 0) + 1, out(0, -1) + out(0, 1) + 1];
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_every_control_is_big_enough_to_tap(page: Page, live_server, viewport, lang, tab):
    """A tap reaches 44x44px on a phone and a click 24x24px on a desktop, however slim the control looks.

    Measured where a tap lands, not by the frame: an invisible zone around a slim pill counts, and
    a neighbour's zone lying over it shortens it.
    """
    _open(page, live_server, viewport, lang, tab)
    page.mouse.move(0, 0)
    least = TAP[viewport]
    small = []
    for control in page.locator(HEADER).locator(CONTROLS).all():
        wide, high = control.evaluate(_REACH)
        if wide < least or high < least:
            small.append((control.evaluate(_DESCRIBE)["key"], wide, high))
    found = [f"tap/{viewport}/{lang}/{tab}/{key}" for key, _, _ in small]
    assert not _breaks(found), [f"{key}: reaches {wide}x{high}px, not {least}" for key, wide, high in small]


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
  // The lines as drawn: how many, and how far apart (so a line-height of normal is read too). A
  // line is told apart by its rounded top; the distance is taken from the exact tops, since 13px
  // type spaced 1.2 sits 15.6px apart, which rounding would read as 15.
  const rows = new Map();
  for (const q of rects) { const k = Math.round(q.top); rows.set(k, Math.min(rows.get(k) ?? Infinity, q.top)); }
  const tops = [...rows.keys()].sort((a, b) => a - b).map(k => rows.get(k));
  const lines = tops.length;
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
          spacing: lines > 1 ? (tops[1] - tops[0]) / parseFloat(s.fontSize) : 0};
}
"""
SIDE, END, LINES, SPACING = 8, 4, 2, 1.2


def _label_faults(label, minimal):
    """What is wrong with where a label's words sit; at 320px and on tablets only what spills over."""
    if minimal:
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
@pytest.mark.parametrize("viewport", [*VIEWPORTS, *MINIMAL])
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_every_label_fits_its_control(page: Page, live_server, viewport, lang, tab):
    """Words stay inside their frame with room around them, in all three languages, from 360px up.

    Kazakh is usually the longest. At most two lines, spaced at least 1.2 apart; at least 8px from the
    frame at the sides and 4px above and below -- a word cut off, spilling out or touching the frame
    reads as a broken button. At 320px and on tablets only what is cut off or spills over counts.
    """
    _open(page, live_server, viewport, lang, tab)
    found, details = [], []
    for control in page.locator(HEADER).locator(CONTROLS).all():
        label = control.evaluate(_LABEL)
        if label is None:
            continue
        key, name, scroll, client = (control.evaluate(_DESCRIBE)[k] for k in ("key", "name", "scroll", "client"))
        faults = [f"{scroll}px in {client}px"] if scroll > client else []
        faults += _label_faults(label, viewport in MINIMAL)
        if faults:
            found.append(f"fits/{viewport}/{lang}/{tab}/{key}")
            details.append(f"{key} ({name!r}): " + ", ".join(faults))
    assert not _breaks(found), "\n".join(details)


# Words of four letters or more that a narrow column broke across lines: their pieces stand at more
# than one height. A word the page hyphenates itself (a hyphen, a dash, a soft hyphen) is left out.
_BROKEN = """
() => {
  const broken = [];
  const walk = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT);
  for (let node = walk.nextNode(); node && broken.length < 5; node = walk.nextNode()) {
    if (!node.parentElement || !node.parentElement.offsetParent) continue;
    for (const match of node.textContent.matchAll(/[^\\s\\-\u2010-\u2015\u00ad]{4,}/g)) {
      const range = document.createRange();
      range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length);
      const tops = new Set([...range.getClientRects()].filter(q => q.width > 0).map(q => Math.round(q.top)));
      if (tops.size > 1) { broken.push(match[0]); if (broken.length >= 5) break; }
    }
  }
  return broken;
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport", [*VIEWPORTS, *MINIMAL])
@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("tab", TABS)
def test_no_word_breaks_into_letters(page: Page, live_server, race_event_type, organizer, viewport, lang, tab):
    """A column too narrow for its words breaks them a letter or two to a line; it reads as noise.

    An event is on the page so that the list has rows to measure.
    """
    event = Competition.objects.create(
        title_ru="Gran Fondo Alatau",
        title_en="Gran Fondo Alatau",
        submitted_by=organizer,
        date_start=datetime.date.today() + datetime.timedelta(days=3),
        status=Competition.Status.APPROVED,
    )
    event.event_types.add(race_event_type)
    _open(page, live_server, viewport, lang, tab)
    broken = page.evaluate(_BROKEN)
    found = [f"letters/{viewport}/{lang}/{tab}"] if broken else []
    assert not _breaks(found), f"words broken across lines: {broken}"


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
    groups = page.evaluate(_ROWS)
    assert groups, "the header has no button group to measure"
    folded = [group for group in groups if len(group["tops"]) > 1]
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
    """Put a control at rest or under the pointer, and wait for its fade to finish."""
    page.mouse.move(0, 0)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    if state == "hover":
        control.hover()
    # A colour read mid-fade is neither state's.
    control.evaluate("el => Promise.all(el.getAnimations().map(a => a.finished.catch(() => {})))")


# Whether a control shows words: an icon button whose label is hidden on a phone shows none.
_WORDS = "el => !!el.innerText.trim()"

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
    """The words of the header's controls at rest and under the pointer, as test_skin_contrast.py measures.

    A control with no words (an icon alone) is test_every_border_can_be_seen's.
    """
    _open(page, live_server, viewport, "ru", tab)
    skin = settings.DEFAULT_SKIN
    found, details = [], []
    for control in page.locator(HEADER).locator(CONTROLS).all():
        if not control.is_enabled() or not control.evaluate(_WORDS):
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
    """A control with no words is found by its outline: 3:1 against what surrounds it (WCAG 1.4.11).

    A field or a checkbox by its boundary, a button that is an icon alone by the icon. A control
    with words is known by them, and its border may be as light as the skin draws it.
    """
    _open(page, live_server, viewport, "ru", tab)
    skin = settings.DEFAULT_SKIN
    found, details = [], []
    page.mouse.move(0, 0)
    for control in page.locator(HEADER).locator(CONTROLS).all():
        if control.evaluate(_WORDS):
            continue
        key = control.evaluate(_DESCRIBE)["key"]
        if control.evaluate("el => el.matches('input, select, textarea')"):
            frame = _frame(control)
            value = ratio(frame, drawn(control, "fill-beneath")) if frame else 1.0
            what = "boundary"
        else:
            value, what = legibility(control), "icon"
        if value < 3:
            found.append(f"border/{skin}/{viewport}/{tab}/{key}")
            details.append(f"{key} ({what}): {value:.2f} < 3")
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
    assert selected.count(), "nothing in the header is marked selected"
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
    found = [f"frame/{viewport}/{tab}"] if len(set(borders)) > 1 else []
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
