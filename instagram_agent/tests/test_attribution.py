"""What a published event may say about where it came from -- and what it may never say.

The site's maintainer is a Russian citizen and the platform these accounts live on is designated
extremist in Russia. A published event therefore credits the account by name and nothing else: no
platform, no post link, anywhere. These tests exist because a prompt can be forgotten mid-reply and
this must not depend on the model getting it right.
"""

from agent.models import Candidate
from instagram_agent.accounts import Account
from instagram_agent.attribution import credit_account

ACCOUNT = Account("ubtalmaty", city="Almaty")
# "Istochnik obyavleniya" -- the credit line, spelled from code points to keep this file ASCII-only.
CREDIT_RU = "".join(chr(c) for c in (0x418, 0x441, 0x442, 0x43E, 0x447, 0x43D, 0x438, 0x43A))


def _candidate(**kwargs):
    base = {
        "title": "Early Bird Coffee Ride",
        "date_start": "2026-08-08",
        "description": "<p>Gather at 5:45</p>",
        "description_kk": "<p>Zhinalu 5:45</p>",
        "description_en": "<p>Gather at 5:45</p>",
    }
    return Candidate(**{**base, **kwargs})


def test_the_account_is_credited_at_the_end_of_every_locale():
    credited = credit_account(_candidate(), ACCOUNT)
    for text in (credited.description, credited.description_kk, credited.description_en):
        assert text.rstrip().endswith("@ubtalmaty</p>")
    assert f"{CREDIT_RU} " in credited.description


def test_the_credit_says_the_account_and_not_where_it_is():
    credited = credit_account(_candidate(), ACCOUNT)
    assert "@ubtalmaty" in credited.description
    for banned in ("instagram", "insta", "http"):
        assert banned not in credited.description.lower()


def test_the_post_link_never_reaches_the_event():
    credited = credit_account(_candidate(source_url="https://www.instagram.com/p/Abc123/"), ACCOUNT)
    assert credited.source_url == ""


def test_a_route_or_registration_link_is_dropped_too():
    """Both are shown on the event page, and the only link a post offers is back into the platform."""
    credited = credit_account(
        _candidate(url_route="https://instagram.com/p/x/", url_registration="https://instagram.com/p/y/"), ACCOUNT
    )
    assert (credited.url_route, credited.url_registration) == ("", "")


def test_a_link_the_model_wrote_into_the_description_is_removed():
    described = _candidate(description='<p>Details in <a href="https://www.instagram.com/p/Abc/">the post</a></p>')
    credited = credit_account(described, ACCOUNT)
    assert "instagram.com" not in credited.description
    assert "href" not in credited.description
    assert "the post" in credited.description  # the sentence survives, only the link goes


def test_a_bare_url_in_the_text_is_removed():
    credited = credit_account(_candidate(description="<p>See https://instagram.com/ubtalmaty</p>"), ACCOUNT)
    assert "http" not in credited.description
    assert "instagram" not in credited.description.lower()


def test_the_platform_named_in_a_title_is_removed():
    credited = credit_account(_candidate(title="Ride announced on Instagram"), ACCOUNT)
    assert "instagram" not in credited.title.lower()
    assert "Ride announced on" in credited.title


def test_the_platform_named_in_cyrillic_is_removed_too():
    # The same word as a caption would write it in Russian.
    cyrillic = "".join(chr(c) for c in (0x418, 0x43D, 0x441, 0x442, 0x430, 0x433, 0x440, 0x430, 0x43C))
    credited = credit_account(_candidate(description=f"<p>{cyrillic}: @ubtalmaty</p>"), ACCOUNT)
    assert cyrillic.lower() not in credited.description.lower()


def test_an_empty_description_still_gets_its_credit():
    credited = credit_account(_candidate(description="", description_kk="", description_en=""), ACCOUNT)
    assert credited.description == f"<p>{CREDIT_RU} " + credited.description.split(f"{CREDIT_RU} ")[1]
    assert "@ubtalmaty" in credited.description_en


def test_scrubbing_does_not_leave_an_empty_paragraph_behind():
    credited = credit_account(_candidate(description="<p>https://instagram.com/p/x/</p><p>Real text</p>"), ACCOUNT)
    assert "<p></p>" not in credited.description
    assert "Real text" in credited.description


def test_everything_else_about_the_event_is_left_alone():
    credited = credit_account(_candidate(city="Almaty", venue="Giant Abay 47"), ACCOUNT)
    assert (credited.date_start, credited.city, credited.venue) == ("2026-08-08", "Almaty", "Giant Abay 47")
    assert credited.title == "Early Bird Coffee Ride"


def test_an_image_the_model_embedded_is_removed_with_its_tag():
    """No picture from a post reaches the site: not stored, not linked, not hotlinked.

    Nothing collects media in the first place -- the reader never reads those fields -- but a model
    can write an <img> into a description, and a hotlinked image puts the platform on the page as
    surely as its name does.
    """
    described = _candidate(description='<p>Look</p><img src="https://instagram.fxyz.fna.fbcdn.net/v/t51.jpg">')
    credited = credit_account(described, ACCOUNT)
    assert "<img" not in credited.description
    assert "fbcdn" not in credited.description
    assert "Look" in credited.description


def test_an_embedded_video_or_frame_goes_with_its_contents():
    described = _candidate(
        description='<p>Ride</p><video src="https://cdn.example/x.mp4">fallback</video>'
        '<iframe src="https://www.instagram.com/p/Abc/embed"></iframe>'
    )
    credited = credit_account(described, ACCOUNT)
    for tag in ("<video", "<iframe", "fallback", "cdn.example"):
        assert tag not in credited.description
    assert "Ride" in credited.description
