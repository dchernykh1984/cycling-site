"""E2E tests for the rich-text competition description editor (Quill).

These run a real browser, so they catch rendering bugs that string-level Django
template tests cannot -- e.g. a leaking template comment that injected a phantom
``.quill-editor`` box which Quill then initialised over the stylesheet ``<link>``,
leaving every toolbar unstyled (giant SVG icons). The HTML still *contained* the
right strings, so ``assertContains`` stayed green; only a browser reveals it.
"""

import datetime

import pytest
from playwright.sync_api import Page, expect

from calendar_app.models import Competition
from tests.e2e.conftest import inject_session, switch_locale


def _header_label_text(page: Page) -> str:
    # ::before carries the (localized) heading-picker label; quoted by getComputedStyle.
    return page.locator(".ql-picker.ql-header .ql-picker-label").first.evaluate(
        "el => getComputedStyle(el, '::before').content"
    )


# Reading ``cssRules`` only succeeds for a same-origin stylesheet that actually
# loaded and parsed; if the snow ``<link>`` was removed/never applied this is null.
_SNOW_LOADED = """() => {
  const s = [...document.styleSheets].find(x => x.href && x.href.includes('quill.snow'));
  try { return s ? s.cssRules.length : 0; } catch (e) { return -1; }
}"""


def _assert_editor_healthy(page: Page) -> None:
    # Exactly three editors (ru/kk/en) -- a fourth means a phantom box leaked in.
    expect(page.locator(".ql-toolbar")).to_have_count(3)
    expect(page.locator(".ql-container")).to_have_count(3)
    # The snow stylesheet must be loaded and applied.
    assert page.evaluate(_SNOW_LOADED) > 0, "quill.snow.css is not loaded/applied"
    # With the theme applied, the toolbar is a thin bar and icons are small; an
    # unstyled toolbar blows the SVG icons up to hundreds of px.
    box = page.evaluate(
        """() => {
          const tb = document.querySelector('.ql-toolbar');
          const svg = document.querySelector('.ql-toolbar svg');
          return {
            toolbarH: tb ? tb.getBoundingClientRect().height : null,
            svgW: svg ? svg.getBoundingClientRect().width : null,
          };
        }"""
    )
    assert box["toolbarH"] is not None and box["toolbarH"] < 120, box
    assert box["svgW"] is not None and box["svgW"] < 40, box
    # The shared partial must give the editable area a real min-height; regression guard against a
    # `.quill-editor .ql-container` descendant rule that never matched (collapsing the field to 0).
    min_h = page.evaluate(
        "() => parseInt(getComputedStyle(document.querySelector('.quill-editor .ql-editor')).minHeight) || 0"
    )
    assert min_h >= 100, f"editor min-height not applied: {min_h}"


@pytest.mark.django_db(transaction=True)
def test_submit_editor_renders_with_snow_theme(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    _assert_editor_healthy(page)


@pytest.mark.django_db(transaction=True)
def test_submit_editor_is_typeable_and_fills_hidden_field(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    editor = page.locator("#quill-desc-ru .ql-editor")
    editor.click()
    editor.type("Hello editor")
    expect(editor).to_contain_text("Hello editor")
    # The submit handler copies the editor HTML into the hidden field; simulate it on
    # the competition form (the page also has navbar language-switcher forms).
    page.evaluate("() => document.getElementById('id_description_ru').form.dispatchEvent(new Event('submit'))")
    value = page.input_value("#id_description_ru")
    assert "Hello editor" in value


@pytest.mark.django_db(transaction=True)
def test_submit_round_trips_all_three_locales(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    page.fill("#id_title_ru", "Trilingual Race")
    page.fill("#id_date_start", "2026-09-01")
    # The kk/en editors live in hidden tab-panes; switch to each before typing.
    for loc, tab, text in (
        ("ru", "#tab-ru", "Russian body"),
        ("kk", "#tab-kk", "Kazakh body"),
        ("en", "#tab-en", "English body"),
    ):
        page.click(f'button[data-bs-target="{tab}"]')
        editor = page.locator(f"#quill-desc-{loc} .ql-editor")
        editor.click()
        editor.type(text)
    # Return to the RU tab so the required title field is in the visible pane: WebKit
    # refuses to submit a form whose required control sits in a display:none tab pane.
    page.click('button[data-bs-target="#tab-ru"]')
    page.click('form[enctype="multipart/form-data"] button[type=submit]')
    page.wait_for_load_state("networkidle")

    comp = Competition.objects.get(title_ru="Trilingual Race")
    assert "Russian body" in comp.description_ru
    assert "Kazakh body" in comp.description_kk
    assert "English body" in comp.description_en


@pytest.mark.django_db(transaction=True)
def test_submit_strips_script_from_editor_html(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    page.fill("#id_title_ru", "XSS Race")
    page.fill("#id_date_start", "2026-09-01")
    # Put markup containing a script into the editor's live DOM (as a malicious paste
    # could); the submit handler copies quill.root.innerHTML into the hidden field, and the
    # server must strip the script on save.
    page.evaluate(
        """() => {
          const ed = document.querySelector('#quill-desc-ru .ql-editor');
          ed.innerHTML = '<p>safe text</p><script>window.__x=1<\\/script>';
        }"""
    )
    page.click('form[enctype="multipart/form-data"] button[type=submit]')
    page.wait_for_load_state("networkidle")

    comp = Competition.objects.get(title_ru="XSS Race")
    assert "safe text" in comp.description_ru
    assert "<script" not in comp.description_ru.lower()


@pytest.mark.django_db(transaction=True)
def test_heading_picker_labels_are_localized(page: Page, live_server, organizer):
    # Asserted structurally (no Cyrillic literals in .py): en keeps Quill's upstream
    # "Normal"; ru and kk are each localized to a distinct non-English label.
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/submit/")
    ru = _header_label_text(page)  # default UI locale is ru (autouse cookie fixture)
    switch_locale(page, "en")
    en = _header_label_text(page)
    switch_locale(page, "kk")
    kk = _header_label_text(page)
    assert "Normal" in en
    assert "Normal" not in ru and "Normal" not in kk
    assert ru != kk


@pytest.mark.django_db(transaction=True)
def test_edit_editor_prefills_existing_description(page: Page, live_server, organizer):
    comp = Competition.objects.create(
        title_ru="Editor Prefill Race",
        date_start=datetime.date(2026, 9, 1),
        submitted_by=organizer,
        status=Competition.Status.APPROVED,
        description_ru="<p>Existing <strong>rich</strong> description</p>",
    )
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/calendar/{comp.pk}/edit/")
    _assert_editor_healthy(page)
    expect(page.locator("#quill-desc-ru .ql-editor")).to_contain_text("Existing rich description")
