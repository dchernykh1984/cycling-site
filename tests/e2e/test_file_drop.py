"""A file dragged onto its field instead of picked by its button, on a computer: the event form's documents
and the event assistant's chat. A phone, with nothing to drag, is not told it may."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import inject_session
from tests.e2e.test_event_assistant import _model

# Lets go of a file named ``name`` over the zone -- ``selector``, or its block ``within`` it sits in -- as
# a mouse would; the result is whether the zone was marked while the file was over it, and only then.
DROP = """([selector, within, name, type]) => {
  const field = document.querySelector(selector), zone = within ? field.closest(within) : field;
  const carried = new DataTransfer();
  carried.items.add(new File(['%PDF-1.4'], name, { type }));
  const fire = kind => zone.dispatchEvent(
    new DragEvent(kind, { dataTransfer: carried, bubbles: true, cancelable: true }));
  fire('dragenter');
  const marked = zone.classList.contains('file-drop-over');
  fire('dragover');
  fire('drop');
  return marked && !zone.classList.contains('file-drop-over');
}"""


@pytest.fixture
def chat_on(settings):
    settings.ASSISTANT_LLM_API_KEY = "sk-test"


def _desktop(page: Page) -> bool:
    return page.evaluate("matchMedia('(hover: hover) and (pointer: fine)').matches")


@pytest.mark.django_db(transaction=True)
def test_a_file_dropped_on_a_documents_field_is_its_file(page: Page, live_server, organizer):
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    hint = page.get_by_text("A file can also be dragged onto its field.")
    if not _desktop(page):
        expect(hint).to_be_hidden()
        pytest.skip("a phone has nothing to drag")
    expect(hint).to_be_visible()
    zone = "#id_file_regulations"
    assert page.evaluate(DROP, [zone, ".mb-3", "rules.pdf", "application/pdf"])
    assert page.eval_on_selector(zone, "i => i.files.length ? i.files[0].name : ''") == "rules.pdf"
    assert page.eval_on_selector("#id_file_route", "i => i.files.length") == 0


@pytest.mark.django_db(transaction=True)
def test_a_file_dropped_on_the_assistant_goes_where_the_attach_button_would_put_it(
    page: Page,
    live_server,
    admin_user,
    chat_on,
    monkeypatch,
):
    _model(monkeypatch, {"reply": "Got the regulations.", "set": {}})
    inject_session(page, live_server, admin_user)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    if not _desktop(page):
        pytest.skip("a phone has nothing to drag")
    page.click("#assistant-toggle")
    expect(page.locator("#assistant-drop-hint")).to_be_visible()
    assert page.evaluate(DROP, ["#assistant-panel", None, "rules.docx", "application/octet-stream"])
    expect(page.locator("#assistant-log")).to_contain_text("Attached to the form as the regulations: rules.docx")
    assert page.eval_on_selector("#id_file_regulations", "i => i.files.length ? i.files[0].name : ''") == "rules.docx"


# Lets go of a file over the page outside every zone, and over a file input outside every zone: the
# result is whether each drop was let through to the browser (not cancelled).
OUTSIDE = """() => {
  const carried = new DataTransfer();
  carried.items.add(new File(['x'], 'stray.pdf', { type: 'application/pdf' }));
  const lone = document.createElement('input');
  lone.type = 'file';
  document.body.append(lone);
  const drop = target => target.dispatchEvent(
    new DragEvent('drop', { dataTransfer: carried, bubbles: true, cancelable: true }));
  return [drop(document.querySelector('h1')), drop(lone)];
}"""


@pytest.mark.django_db(transaction=True)
def test_a_file_let_go_past_the_fields_does_not_replace_the_page_and_a_lone_input_still_takes_one(
    page: Page, live_server, organizer
):
    """Dropped on the page, a file would open in its place and lose what was typed; a file input of its
    own, outside every zone, keeps the browser's own way of taking a dropped file."""
    inject_session(page, live_server, organizer)
    page.goto(f"{live_server.url}/en/calendar/submit/")
    if not _desktop(page):
        pytest.skip("a phone has nothing to drag")
    on_page, on_input = page.evaluate(OUTSIDE)
    assert on_page is False  # cancelled: nothing opens in place of the form
    assert on_input is True  # let through: the input's own drop stands
