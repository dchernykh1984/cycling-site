"""Reading an event's own link off the page it was found on.

A calendar or a forum lists every race as a link whose text is the race's name. When the model
leaves the announcement link empty -- which it does often enough to matter -- that list still holds
the answer, and it is already in the text the model was given. Events 632, 633 and 634 went out
with no link at all while the page they came from named each of them.
"""

import pytest

from agent.links import LINKS_MARKER, labelled_links, link_for_title

PAGE = (
    "HOOP Enduro Series #3 / Final (Yalgora): 28.08.2026 - 30.08.2026"
    + LINKS_MARKER
    + "\n".join(
        [
            "Forum home - https://forum.velomania.ru/",
            "HOOP Enduro Series #3 / Final (Yalgora) - https://forum.velomania.ru/calendar.php?do=getinfo&e=885",
            "GUBAHA DOWNHILL RACE - https://forum.velomania.ru/calendar.php?do=getinfo&e=884",
            "Registration - https://forum.velomania.ru/register.php",
        ]
    )
)


class TestReadingTheList:
    def test_every_labelled_link_is_read_back(self):
        pairs = labelled_links(PAGE)
        assert ("GUBAHA DOWNHILL RACE", "https://forum.velomania.ru/calendar.php?do=getinfo&e=884") in pairs
        assert len(pairs) == 4

    def test_a_page_with_no_list_yields_nothing(self):
        assert labelled_links("Just some text about a race") == []

    def test_a_label_containing_a_dash_keeps_its_whole_name(self):
        """The separator also occurs inside race names, so the URL is taken from the end."""
        text = LINKS_MARKER + "Gran Fondo - Almaty - 2026 - https://example.kz/gf"
        assert labelled_links(text) == [("Gran Fondo - Almaty - 2026", "https://example.kz/gf")]


class TestPickingTheLink:
    def test_the_race_named_exactly_wins(self):
        got = link_for_title("HOOP Enduro Series #3 / Final (Yalgora)", labelled_links(PAGE))
        assert got == "https://forum.velomania.ru/calendar.php?do=getinfo&e=885"

    def test_spelling_differences_do_not_break_the_match(self):
        """Punctuation, case and spacing differ between a title and the anchor that names it."""
        got = link_for_title("hoop enduro series 3 / final (yalgora)", labelled_links(PAGE))
        assert got == "https://forum.velomania.ru/calendar.php?do=getinfo&e=885"

    def test_a_longer_anchor_still_matches_the_title_inside_it(self):
        links = [("Registration for GUBAHA DOWNHILL RACE 2026", "https://example.ru/gubaha")]
        assert link_for_title("GUBAHA DOWNHILL RACE", links) == "https://example.ru/gubaha"

    def test_the_most_specific_match_wins(self):
        links = [
            ("Cup", "https://example.ru/cup"),
            ("Ural Cup stage 3 downhill", "https://example.ru/ural-3"),
        ]
        assert link_for_title("Ural Cup stage 3 downhill", links) == "https://example.ru/ural-3"

    def test_an_unrelated_link_is_never_offered(self):
        """A wrong link is worse than none: it sends the reader confidently to another race."""
        assert link_for_title("Almaty Marathon 2026", labelled_links(PAGE)) == ""

    def test_a_listing_is_not_offered_even_when_its_name_matches(self):
        links = [("Forum velomania", "https://forum.velomania.ru/")]
        assert link_for_title("Forum velomania", links) == ""

    @pytest.mark.parametrize("title", ["", "Race", "10 km"])
    def test_a_name_too_short_to_identify_anything_matches_nothing(self, title):
        links = [("Race", "https://example.ru/race"), ("10 km", "https://example.ru/10km")]
        assert link_for_title(title, links) == ""
