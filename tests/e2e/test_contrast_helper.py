"""The contrast helper (tests/e2e/contrast.py) reads colours as they reach the screen."""

import pytest
from playwright.sync_api import Error, Page

from tests.e2e.contrast import drawn, painted, ratio

PAGE = """<body style="margin:0;background:#000">
<p id="faint" style="color:rgba(255,255,255,0.1)">faint</p>
<div style="background:rgba(255,255,255,0.5)"><p id="on-half">text</p></div>
</body>"""


@pytest.fixture
def black_page(page: Page):
    page.set_content(PAGE)
    return page


@pytest.mark.django_db
def test_a_see_through_colour_is_blended_with_what_lies_beneath(black_page):
    faint = black_page.locator("#faint")
    # The colour value alone reads as white on black, 21:1; drawn, it is barely there.
    assert ratio(drawn(faint), drawn(faint, "fill")) < 1.3
    assert drawn(black_page.locator("#on-half"), "fill") in ([127, 127, 127], [128, 128, 128])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("colour", "expected"),
    [
        ("rgb(10, 20, 30)", [10, 20, 30]),
        ("oklch(1 0 0)", [255, 255, 255]),
        ("color(display-p3 1 1 1)", [255, 255, 255]),
    ],
)
def test_any_format_the_browser_reads_comes_out_as_srgb(black_page, colour, expected):
    assert painted(black_page, colour) == expected


@pytest.mark.django_db
def test_a_colour_the_browser_cannot_read_is_an_error_not_a_pass(black_page):
    with pytest.raises(Error, match="unknown colour format"):
        painted(black_page, "not-a-colour")
