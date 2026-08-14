"""Taking the click-id off a link the announcement carried."""

from agent.links import is_tracking, strip_tracking

# The link that failed two nightly runs: a Google form copied out of Facebook. 294 characters against
# a varchar(200) column, of which 194 are the click-id.
REAL_FAILURE = (
    "https://docs.google.com/forms/d/e/1FAIpQLSc1vdZvuul6bGC66IHZQ76mxiYPK6b-r791MzlxEm0dSYXpLQ/viewform"
    "?fbclid=PAcGRvZgJmZGlkFlDFjspEsRZyucFotTcNTiZvdmylLLlleHRuA2FlbQIxMQBzcnRjBmFwcF9pZA8xMjQwMjQ1NzQyODc0MTQ"
    "AAafmfymQZ_go2oqqMcAK39pFgGqRUMmeqvKjK3EOr3kTu-7qRxINoVr4_2h7fg_aem_0z2Kl-IN9I51erXLw1YqPg"
)


def test_the_link_that_broke_a_run_now_fits_a_column():
    cleaned = strip_tracking(REAL_FAILURE)
    assert len(REAL_FAILURE) == 294
    assert cleaned == (
        "https://docs.google.com/forms/d/e/1FAIpQLSc1vdZvuul6bGC66IHZQ76mxiYPK6b-r791MzlxEm0dSYXpLQ/viewform"
    )
    assert len(cleaned) <= 200


def test_every_family_of_click_id_comes_off():
    for key in ("fbclid", "gclid", "yclid", "igshid", "msclkid", "ttclid", "mc_cid", "si"):
        assert is_tracking(key), key
        assert strip_tracking(f"https://example.com/page?{key}=abc123") == "https://example.com/page"


def test_the_utm_family_comes_off_whatever_it_is_called():
    """utm_ generates a name per campaign, so the family is matched rather than each member."""
    url = "https://example.com/race?utm_source=tg&utm_medium=post&utm_campaign=spring&utm_whatever=x"
    assert strip_tracking(url) == "https://example.com/race"


def test_a_parameter_that_chooses_the_page_is_kept():
    """A query is how a page is chosen as often as it is how a click is counted."""
    url = "https://example.com/results?event=42&year=2026"
    assert strip_tracking(url) == url


def test_a_kept_parameter_survives_beside_a_dropped_one():
    url = "https://example.com/form?entry=7&fbclid=xyz&page=2"
    assert strip_tracking(url) == "https://example.com/form?entry=7&page=2"


def test_the_order_of_what_is_kept_does_not_change():
    """Some services read their query positionally; reordering it would be a different request."""
    url = "https://example.com/x?b=2&utm_source=t&a=1"
    assert strip_tracking(url) == "https://example.com/x?b=2&a=1"


def test_the_part_that_decides_where_the_link_goes_is_never_touched():
    url = "https://sub.example.com:8443/path/to/page?fbclid=x#section-3"
    assert strip_tracking(url) == "https://sub.example.com:8443/path/to/page#section-3"


def test_a_link_with_nothing_to_strip_comes_back_identical():
    for url in ("https://example.com/", "https://example.com/a/b", "https://example.com/x?a=1"):
        assert strip_tracking(url) == url


def test_something_that_is_not_a_web_link_is_left_alone():
    """A mailto: or a bare handle is not ours to rewrite -- and has no query to clean anyway."""
    for value in ("", "mailto:someone@example.com?subject=Race", "@channel", "not a url at all"):
        assert strip_tracking(value) == value


def test_a_blank_value_of_a_kept_parameter_stays_blank_rather_than_vanishing():
    """Dropping "?q=" would change what is asked for on services that treat it as an empty search."""
    assert strip_tracking("https://example.com/s?q=&fbclid=z") == "https://example.com/s?q="


def test_matching_ignores_the_case_the_parameter_was_written_in():
    assert strip_tracking("https://example.com/x?FBCLID=abc") == "https://example.com/x"
