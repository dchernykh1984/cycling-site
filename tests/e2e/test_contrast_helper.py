"""The contrast helper (tests/e2e/contrast.py) reads colours as they reach the screen."""

import pytest
from playwright.sync_api import Error, Page

from tests.e2e.contrast import drawn, legibility, painted, ratio

# A 1x1 white SVG as a background picture.
WHITE_PICTURE = (
    "data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%221%22 height=%221%22>"
    "<rect width=%221%22 height=%221%22 fill=%22white%22/></svg>"
)
PAGE = f"""<body style="margin:0;background:#000">
<p id="faint" style="color:rgba(255,255,255,0.1)">faint</p>
<div style="background:rgba(255,255,255,0.5)"><p id="on-half">text</p></div>
<p id="shadow" style="color:transparent;text-shadow:0 0 0 rgb(10, 20, 30)">drawn as a shadow</p>
<div style="background:#fff">
  <p id="faded" style="color:#000;opacity:0.1">faded text</p>
  <div style="opacity:0.1"><p id="in-faded" style="color:#000">text in a faded block</p></div>
  <p id="filtered" style="color:#000;filter:blur(1px)">blurred</p>
</div>
<p id="on-image" style="color:#fff;background-image:url('{WHITE_PICTURE}')">white on a white picture</p>
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


@pytest.mark.django_db
def test_text_drawn_as_its_own_shadow_reads_as_the_shadow_colour(black_page):
    # How Bootstrap shows a focused select's text in Firefox.
    assert drawn(black_page.locator("#shadow")) == [10, 20, 30]


@pytest.mark.django_db
@pytest.mark.parametrize("element", ["#faded", "#in-faded"])
def test_opacity_on_the_text_or_an_ancestor_fades_it_into_its_backdrop(black_page, element):
    # Black on white reads 21:1 by its colours; at a tenth of its opacity it is barely there.
    assert legibility(black_page.locator(element)) < 1.4


@pytest.mark.django_db
def test_a_way_of_drawing_a_flat_colour_cannot_stand_for_is_an_error(black_page):
    with pytest.raises(Error, match="cannot judge contrast through filter"):
        drawn(black_page.locator("#filtered"))


@pytest.mark.django_db
def test_text_over_a_background_picture_is_an_error_not_a_pass(black_page):
    # White text, white picture under it: the colours alone would say 21:1.
    with pytest.raises(Error, match="cannot judge contrast through a background image"):
        legibility(black_page.locator("#on-image"))
