"""The head of every page, as a crawler reads it.

Before this, all 500+ competition pages carried the same description -- "Cycling events, news and
knowledge base" -- and no canonical at all, so nothing distinguished one event from another in a
search index. The title was also rendered across several template lines, which Django keeps, so it
began with blank lines.
"""

import datetime
import io
import re
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext
from django.utils.translation import override as translation_override
from PIL import Image

from calendar_app.models import Competition
from cycling_site import skins
from tests.language_urls import in_language

DEFAULT_DESCRIPTION = (
    "Calendar of endurance sport events -- cycling, running, cross-country skiing -- in "
    "Kazakhstan, Kyrgyzstan, Russia and beyond. Announcements, results and a knowledge base."
)


def _competition(title="Race", **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": datetime.date.today() + datetime.timedelta(days=10),
        "status": Competition.Status.APPROVED,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


def _meta(html, name):
    m = re.search(rf'<meta[^>]+name="{name}"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else None


def _prop(html, prop):
    m = re.search(rf'<meta[^>]+property="{prop}"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else None


class TitleShapeTests(TestCase):
    def test_the_title_has_no_stray_whitespace(self):
        comp = _competition("Tidy title race")
        html = self.client.get(comp.get_absolute_url()).content.decode()
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        self.assertEqual(title, title.strip())
        self.assertNotIn("\n", title)


class SharedTitleTests(TestCase):
    """The title a chat shows for a link (issue #334): the page's own name, the one its tab shows.

    The calendar's tabs and the home page name themselves in their templates' title block; og:title
    read only what a view passed, so a chat showed nothing for the calendar and "Home" for the site.
    """

    def _titles(self, url):
        html = self.client.get(url).content.decode()
        return re.search(r"<title>(.*?)</title>", html, re.S).group(1), _prop(html, "og:title")

    def test_the_home_page_and_the_calendar_s_tabs_are_shared_under_their_own_names(self):
        from home.models import SiteContent

        SiteContent.objects.update_or_create(pk=1, defaults={"page_title_ru": "UBT"})
        for skin in ("light", "orange"):
            with override_settings(DEFAULT_SKIN=skin):
                for url in ("/ru/", reverse("calendar"), reverse("calendar_list"), reverse("calendar_map")):
                    title, shared = self._titles(url)
                    self.assertTrue(shared, (skin, url))
                    self.assertTrue(title.startswith(shared), (skin, url, title, shared))
                self.assertEqual(self._titles("/ru/")[1], "UBT", skin)

    def test_a_name_the_view_gives_still_wins(self):
        comp = _competition("Named race")
        self.assertEqual(_prop(self.client.get(comp.get_absolute_url()).content.decode(), "og:title"), "Named race")


class CanonicalTests(TestCase):
    def test_every_page_declares_a_canonical_address(self):
        comp = _competition("Canonical race")
        html = self.client.get(comp.get_absolute_url()).content.decode()
        m = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]*)"', html)
        self.assertIsNotNone(m)
        self.assertTrue(m.group(1).endswith(comp.get_absolute_url()))


class DefaultDescriptionTests(TestCase):
    def test_the_fallback_names_more_than_cycling(self):
        """The old default said "cycling" only, on a site that also lists running and skiing."""
        page = self.client.get(in_language(reverse("calendar"), "en"), HTTP_ACCEPT_LANGUAGE="en")
        description = _meta(page.content.decode(), "description")
        self.assertIsNotNone(description)
        lowered = description.lower()
        for word in ("running", "skiing", "kazakhstan"):
            self.assertIn(word, lowered)

    def test_the_fallback_is_translated(self):
        """A string left untranslated -- or marked fuzzy, which gettext ignores -- reads as English."""
        for language in ("ru", "kk"):
            with self.subTest(language=language), translation_override(language):
                expected = gettext(DEFAULT_DESCRIPTION)
                self.assertNotEqual(expected, DEFAULT_DESCRIPTION)
                html = self.client.get(
                    in_language(reverse("calendar"), language), HTTP_ACCEPT_LANGUAGE=language
                ).content.decode()
                self.assertIn(escape(expected), html)

    def test_the_same_text_is_used_for_sharing(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertEqual(_meta(html, "description"), _prop(html, "og:description"))


class SocialTagsTests(TestCase):
    def test_a_page_carries_an_image_and_a_card_type(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertTrue((_prop(html, "og:image") or "").endswith(".png"))
        self.assertEqual(_meta(html, "twitter:card"), "summary_large_image")


class CompetitionMetaTests(TestCase):
    """An event page has to say what it is: 500+ of them shared one description before."""

    def setUp(self):
        self.comp = _competition("Almaty Gran Fondo", date_start=datetime.date(2026, 10, 4))

    def _html(self):
        return self.client.get(
            in_language(self.comp.get_absolute_url(), "en"), HTTP_ACCEPT_LANGUAGE="en"
        ).content.decode()

    def test_the_title_is_the_event_name(self):
        self.assertIn("Almaty Gran Fondo", re.search(r"<title>(.*?)</title>", self._html()).group(1))

    def test_the_description_carries_the_name_and_the_date(self):
        description = _meta(self._html(), "description")
        self.assertIn("Almaty Gran Fondo", description)
        self.assertIn("2026", description)

    def test_two_events_do_not_share_a_description(self):
        other = _competition("Astana Night Run", date_start=datetime.date(2026, 5, 1))
        mine = _meta(self._html(), "description")
        theirs = _meta(self.client.get(other.get_absolute_url()).content.decode(), "description")
        self.assertNotEqual(mine, theirs)

    def test_the_description_names_the_place_when_there_is_one(self):
        from locations.models import Location, add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan", name_en="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty", name_en="Almaty")
        venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        self.comp.location = venue
        self.comp.save()
        self.assertIn("Almaty", _meta(self._html(), "description"))
        self.assertIsInstance(venue, Location)


class CompetitionPreviewTextTests(TestCase):
    """What a chat shows under the title of a pasted event link (issue #318).

    The generated summary cannot know when and where riders meet, so an organizer may write that
    line themselves. Search engines keep the summary: the line is written for a chat, not a result.
    """

    def _html(self, comp, language="ru"):
        return self.client.get(
            in_language(comp.get_absolute_url(), language), HTTP_ACCEPT_LANGUAGE=language
        ).content.decode()

    def test_without_one_a_chat_shows_the_summary(self):
        comp = _competition("Saturday ride")
        html = self._html(comp)
        self.assertEqual(_prop(html, "og:description"), _meta(html, "description"))

    def test_with_one_a_chat_shows_it(self):
        comp = _competition("Saturday ride", preview_text_ru="Meet 6:15, start 6:30 at the bike shop")
        self.assertEqual(_prop(self._html(comp), "og:description"), "Meet 6:15, start 6:30 at the bike shop")

    def test_search_engines_still_read_the_summary(self):
        comp = _competition("Saturday ride", preview_text_ru="Meet 6:15, start 6:30 at the bike shop")
        description = _meta(self._html(comp), "description")
        self.assertNotIn("Meet 6:15", description)
        self.assertIn("Saturday ride", description)

    def test_each_language_shows_its_own_line(self):
        comp = _competition(
            "Saturday ride",
            preview_text_ru="Russian line",
            preview_text_kk="Kazakh line",
            preview_text_en="English line",
        )
        for language, expected in (("ru", "Russian line"), ("kk", "Kazakh line"), ("en", "English line")):
            with self.subTest(language=language):
                self.assertEqual(_prop(self._html(comp, language), "og:description"), expected)

    def test_a_language_left_empty_shows_the_date_and_place_in_that_language(self):
        """As the form's hint says: no Russian line in a Kazakh chat, but the summary in Kazakh."""
        comp = _competition("Saturday ride", preview_text_ru="Russian line")
        for language in ("kk", "en"):
            with self.subTest(language=language):
                html = self._html(comp, language)
                self.assertEqual(_prop(html, "og:description"), _meta(html, "description"))
                self.assertNotIn("Russian line", _prop(html, "og:description"))

    def test_so_does_a_tab_the_form_saved_empty(self):
        """The form stores an untouched tab as an empty string, not as NULL."""
        comp = _competition("Saturday ride", preview_text_ru="Russian line", preview_text_kk="", preview_text_en="")
        for language in ("kk", "en"):
            with self.subTest(language=language):
                html = self._html(comp, language)
                self.assertEqual(_prop(html, "og:description"), _meta(html, "description"))

    def test_the_line_is_escaped_inside_the_tag(self):
        comp = _competition("Saturday ride", preview_text_ru='Meet at "Giant" & go')
        self.assertEqual(_prop(self._html(comp), "og:description"), escape('Meet at "Giant" & go'))


class PreviewTextInEverySkinTests(TestCase):
    """A skin may carry its own base.html, and the head lives there. A messenger's bot comes without
    a cookie and gets the default skin, so a copy that forgot og_description hid the organizer's line
    from every chat once that skin became the default (#350 made it orange)."""

    TEXT = "Meet 6:15, start 6:30 by the main entrance"

    def setUp(self):
        self.url = in_language(_competition("Saturday ride", preview_text_ru=self.TEXT).get_absolute_url(), "ru")

    def test_a_bot_without_a_cookie_gets_it(self):
        html = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ru").content.decode()
        self.assertEqual(_prop(html, "og:description"), self.TEXT)

    def test_every_skin_carries_it(self):
        for key in skins.registry():
            with self.subTest(skin=key):
                self.client.cookies[skins.COOKIE] = key
                html = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ru").content.decode()
                self.assertEqual(_prop(html, "og:description"), self.TEXT)


class SocialImageTests(TestCase):
    """What a chat shows when a link is pasted: the site mark, unless a page brings its own."""

    def test_a_page_without_one_falls_back_to_the_site_mark(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertTrue((_prop(html, "og:image") or "").endswith("og-default.png"))
        self.assertEqual(_prop(html, "og:image:width"), "1200")
        self.assertEqual(_prop(html, "og:image:height"), "630")

    def test_the_declared_size_lets_a_messenger_lay_the_card_out_unseen(self):
        """Without these a chat has to fetch the file before it can draw anything."""
        html = self.client.get(reverse("calendar")).content.decode()
        for prop in ("og:image:width", "og:image:height"):
            self.assertIsNotNone(_prop(html, prop), f"{prop} is missing")


# Uploads here write real files; keep them out of the checkout, as the protocol tests do.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CompetitionSocialImageTests(TestCase):
    """An event with a poster of its own should show it, not the site mark, in a chat."""

    def setUp(self):
        self.comp = _competition("Preview Race", date_start=datetime.date(2026, 10, 4))

    def _html(self):
        return self.client.get(self.comp.get_absolute_url()).content.decode()

    @staticmethod
    def _png(size=(600, 400)):
        buffer = io.BytesIO()
        Image.new("RGB", size, "red").save(buffer, format="PNG")
        return SimpleUploadedFile("poster.png", buffer.getvalue(), content_type="image/png")

    def test_an_event_without_one_still_shows_the_site_mark(self):
        self.assertTrue((_prop(self._html(), "og:image") or "").endswith("og-default.png"))

    def test_an_event_with_one_shows_it_instead(self):
        self.comp.preview_image = self._png()
        self.comp.save(update_fields=["preview_image"])
        image = _prop(self._html(), "og:image")
        self.assertIn("competitions/preview/", image)
        self.assertTrue(image.startswith("http"), f"a chat cannot resolve {image!r}")

    def test_the_size_it_declares_is_the_size_of_the_file(self):
        self.comp.preview_image = self._png((640, 480))
        self.comp.save(update_fields=["preview_image"])
        html = self._html()
        self.assertEqual(_prop(html, "og:image:width"), "640")
        self.assertEqual(_prop(html, "og:image:height"), "480")

    def test_a_row_pointing_at_a_missing_file_falls_back_rather_than_breaking(self):
        """Media can go missing; a chat should then get the site mark, not a dead link."""
        self.comp.preview_image = self._png()
        self.comp.save(update_fields=["preview_image"])
        Path(self.comp.preview_image.path).unlink()
        self.assertTrue((_prop(self._html(), "og:image") or "").endswith("og-default.png"))


class LinkPreviewOnThePageTests(TestCase):
    """The preview line lives in a meta tag; whoever can change or approve the event sees it on the page."""

    def setUp(self):
        from accounts.models import User

        self.author = User.objects.create_user(
            username="author@example.com", email="author@example.com", password="pw-123456", role=User.Role.ORGANIZER
        )
        self.moderator = User.objects.create_user(
            username="mod@example.com", email="mod@example.com", password="pw-123456", role=User.Role.ADMIN
        )

    def _page(self, comp, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(in_language(comp.get_absolute_url(), "ru"), HTTP_ACCEPT_LANGUAGE="ru").content.decode()

    def test_the_author_sees_the_line_a_chat_will_show(self):
        comp = _competition("Saturday ride", preview_text_ru="Meet 6:15 at the bike shop", submitted_by=self.author)
        html = self._page(comp, self.author)
        self.assertIn('id="link-preview"', html)
        self.assertIn("Meet 6:15 at the bike shop", html.split('id="link-preview"')[1])

    def test_a_moderator_sees_it_before_approving(self):
        comp = _competition(
            "Saturday ride",
            preview_text_ru="Meet 6:15 at the bike shop",
            submitted_by=self.author,
            status=Competition.Status.PENDING_APPROVAL,
        )
        html = self._page(comp, self.moderator)
        self.assertIn("Meet 6:15 at the bike shop", html.split('id="link-preview"')[1])

    def test_without_a_line_it_shows_the_summary_the_chat_falls_back_to(self):
        comp = _competition("Saturday ride", submitted_by=self.author)
        html = self._page(comp, self.author)
        self.assertIn(_meta(html, "description"), html.split('id="link-preview"')[1])

    def test_a_reader_does_not_see_the_block(self):
        comp = _competition("Saturday ride", preview_text_ru="Meet 6:15 at the bike shop", submitted_by=self.author)
        self.assertNotIn('id="link-preview"', self._page(comp))
