"""The link an event needs is often below the cap the prompt is given.

Event 639 came out with no announcement link while the page it was read from named it: on
forum.velomania.ru the races sit at positions 138-140 of 145 links, and only the first 60 are
quoted to the model. The prompt has to stay readable; the code that matches an event to its own
page has no such budget and should see all of them.
"""

from unittest.mock import patch

from agent import fetch, run, sources
from agent.config import Config
from agent.links import LINKS_MARKER, labelled_links
from agent.models import Candidate, KnownEvents, Taxonomy

FORUM = "https://forum.velomania.ru/"


def _page_with_the_race_last(count: int = 145) -> str:
    """A forum front page: navigation first, the race calendar at the very bottom."""
    navigation = "".join(f'<a href="/forumdisplay.php?f={n}">Section {n}</a>' for n in range(count - 1))
    race = '<a href="/calendar.php?do=getinfo&e=886">Stary Kaluzhsky Trakt</a>'
    return f"<html><body>{navigation}{race}</body></html>"


def _read(html: str, kind: str = "organizer"):
    source = sources.Source(kind=kind, ref="velomania", fetch_url=FORUM)
    with patch("agent.fetch._get_with_fallback", return_value=html):
        return fetch.source_text_and_links(source)


class TestWhatTheReadReturns:
    def test_the_prompt_keeps_its_cap(self):
        text, _ = _read(_page_with_the_race_last())
        assert len(labelled_links(text)) == fetch._MAX_LINKS

    def test_the_races_link_below_the_cap_is_missing_from_the_prompt(self):
        """Its name is on the page and the model reads that; what it cannot see is the address,
        and that is what an event needs. Quoting all 145 links instead would spend the prompt on
        forum navigation."""
        text, _ = _read(_page_with_the_race_last())
        assert all("calendar.php" not in url for _, url in labelled_links(text))

    def test_but_the_full_list_carries_it(self):
        _, every_link = _read(_page_with_the_race_last())
        assert len(every_link) == 145
        assert ("Stary Kaluzhsky Trakt", f"{FORUM}calendar.php?do=getinfo&e=886") in every_link

    def test_the_text_is_still_what_the_model_reads(self):
        text, _ = _read("<html><body><p>Race on Sunday</p><a href='/x'>Somewhere</a></body></html>")
        assert "Race on Sunday" in text
        assert LINKS_MARKER in text


class TestWhatTheEventEndsUpWith:
    def _extract(self, page_links, reply='[{"title": "Stary Kaluzhsky Trakt", "date_start": "2026-08-29"}]'):
        source = sources.Source(kind="organizer", ref="velomania", fetch_url=FORUM)
        config = Config(
            site_base_url="https://site.test",
            api_token="t",
            llm_api_key="k",
            llm_base_url="https://llm.test",
            llm_model="m",
            max_events=10,
            max_per_source=5,
            dry_run=True,
        )
        with patch("agent.llm.extract_raw", return_value=reply):
            return run._extract_candidates("page text", source, "", KnownEvents(), Taxonomy(), config, page_links)

    def test_a_race_named_only_below_the_cap_still_gets_its_link(self):
        _, every_link = _read(_page_with_the_race_last())
        (candidate,) = self._extract(every_link)
        assert candidate.source_url == f"{FORUM}calendar.php?do=getinfo&e=886"

    def test_without_the_list_the_event_is_left_unlinked(self):
        """What happened to event 639, kept as the thing this changes."""
        (candidate,) = self._extract([])
        assert candidate.source_url == ""

    def test_a_link_the_model_found_still_wins(self):
        reply = (
            '[{"title": "Stary Kaluzhsky Trakt", "date_start": "2026-08-29", "source_url": "https://kaluga.ru/race"}]'
        )
        _, every_link = _read(_page_with_the_race_last())
        (candidate,) = self._extract(every_link, reply)
        assert candidate.source_url == "https://kaluga.ru/race"


def test_the_reader_remembers_every_page_it_read():
    """The dictionary the extraction step looks the links up in, filled as each source is read."""
    seen: dict[str, list[tuple[str, str]]] = {}
    read = run._reader(seen)
    source = sources.Source(kind="organizer", ref="velomania", fetch_url=FORUM)
    with patch("agent.fetch._get_with_fallback", return_value=_page_with_the_race_last()):
        read(source)
    assert len(seen["velomania"]) == 145


def test_a_candidate_that_already_has_a_link_is_left_alone():
    candidate = Candidate(title="Stary Kaluzhsky Trakt", date_start="2026-08-29", source_url="https://kept.example/")
    assert run._with_own_link(candidate, "", [("Stary Kaluzhsky Trakt", "https://other.example/x")]) is candidate
