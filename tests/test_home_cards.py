"""The home page's cards: the owner adds, changes, orders and removes them on the site and through
the API, and every skin draws them as tiles -- the site's own skins as cards, UBT Almaty and Dark
UBT their own way."""

import re
import uuid

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from api.tests import ApiTestMixin
from cycling_site import skins
from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
from home.models import HomeCard, SiteContent, localized_cards
from tests.language_urls import in_language

EMPTY_EDITOR = "<p><br></p>"
# The class each skin gives a card's tile, and the one it adds when the first introduces the rest.
TILES = {
    "light": ("card", "home-tile-intro"),
    "dark": ("card", "home-tile-intro"),
    "orange": ("ubt-section", "ubt-section-intro"),
    "ubt-dark": ("ubt-section", "ubt-section-intro"),
}
TILE = r'<section class="([^"]*)">\s*(?:<div class="card-body">\s*)?(?:<h2[^>]*>([^<]*)</h2>)?'


def _member(name, role):
    user = User.objects.create_user(username=name, email=f"{name}@test.local", password="pw", role=role)
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return user


def _card(**fields):
    card = HomeCard(position=HomeCard.next_position(), **fields)
    card.save()
    return card


class HomeCardTests(TestCase):
    def test_a_script_in_a_card_is_stripped_on_save(self):
        card = _card(title_ru="T", body_ru="<p>safe</p><script>alert(1)</script>")
        card.refresh_from_db()
        self.assertIn("safe", card.body_ru)
        self.assertNotIn("<script", card.body_ru.lower())

    def test_an_empty_editor_leaves_the_reader_the_language_the_site_falls_back_to(self):
        _card(title_ru="Heading", body_ru="<p>Text</p>", body_kk=EMPTY_EDITOR, body_en=EMPTY_EDITOR)
        self.assertEqual(localized_cards("kk"), [{"title": "Heading", "body": "<p>Text</p>"}])

    def test_a_text_of_spaces_alone_is_nothing_written(self):
        _card(title_ru="Heading", body_ru="<p>Text</p>", body_kk="<p>&nbsp;</p>", body_en="<p>\u00a0 </p>")
        self.assertEqual(localized_cards("kk")[0]["body"], "<p>Text</p>")
        self.assertEqual(localized_cards("en")[0]["body"], "<p>Text</p>")

    def test_the_plain_columns_hold_the_first_language_written(self):
        card = _card(title_kk="KK heading", body_en="<p>EN text</p>")
        self.assertEqual(card.__dict__["title"], "KK heading")
        self.assertEqual(card.__dict__["body"], "<p>EN text</p>")

    def test_a_new_card_goes_after_the_others(self):
        self.assertEqual(HomeCard.next_position(), 0)
        first = _card(title_ru="A")
        HomeCard.objects.filter(pk=first.pk).update(position=4)
        self.assertEqual(HomeCard.next_position(), 5)

    def test_a_card_moves_to_its_new_place_and_the_others_close_up(self):
        a, b, c = _card(title_ru="A"), _card(title_ru="B"), _card(title_ru="C")
        c.place(0)
        self.assertEqual([card.title_ru for card in HomeCard.objects.all()], ["C", "A", "B"])
        self.assertEqual([card.position for card in HomeCard.objects.all()], [0, 1, 2])
        a.place(99)
        self.assertEqual([card.title_ru for card in HomeCard.objects.all()], ["C", "B", "A"])
        b.place(-3)
        self.assertEqual([card.title_ru for card in HomeCard.objects.all()], ["B", "C", "A"])


class HomePageDrawsTheCardsTests(TestCase):
    def setUp(self):
        SiteContent.objects.update_or_create(pk=1, defaults={"page_title_ru": "UBT", "page_title_kk": "UBT"})
        _card(title_ru="First", title_kk="Birinshi", body_ru="<p>One</p>", body_kk="<p>Bir</p>")
        _card(title_ru="Second", body_ru='<p><a href="/calendar/">calendar</a></p>')

    def _page(self, skin, language="ru"):
        self.client.cookies[skins.COOKIE] = skin
        return self.client.get(f"/{language}/").content.decode()

    def _tiles(self, html):
        """(classes, heading) of each tile in the page's .home-body, in order."""
        body = html[html.index('class="home-body') :]
        return re.findall(TILE, body)

    def test_every_skin_draws_a_tile_for_each_card(self):
        for key, (tile, _) in TILES.items():
            with self.subTest(skin=key):
                html = self._page(key)
                self.assertEqual(self._tiles(html), [(tile, "First"), (tile, "Second")])
                self.assertIn('<a href="/ru/calendar/" rel="noopener" target="_blank">calendar</a>', html)

    def test_each_language_reads_its_own_words_and_falls_back_for_the_rest(self):
        html = self._page("light", "kk")
        self.assertEqual([heading for _, heading in self._tiles(html)], ["Birinshi", "Second"])
        self.assertIn("<p>Bir</p>", html)  # Second has no Kazakh heading yet: the Russian one stands in

    def test_a_first_card_without_a_heading_or_with_the_pages_title_spans_the_row(self):
        for heading in ("", "ubt"):
            HomeCard.objects.all().delete()
            _card(title_ru=heading, body_ru="<p>Intro</p>")
            _card(title_ru="Next", body_ru="<p>More</p>")
            for key, (tile, intro) in TILES.items():
                with self.subTest(heading=heading, skin=key):
                    classes = [classes for classes, _ in self._tiles(self._page(key))]
                    self.assertEqual(classes, [f"{tile} {intro}", tile])

    def test_no_cards_no_text(self):
        HomeCard.objects.all().delete()
        for key in TILES:
            with self.subTest(skin=key):
                self.assertNotIn("home-body", self._page(key))


class OwnerEditsTheCardsTests(TestCase):
    def setUp(self):
        self.owner = _member("owner", User.Role.OWNER)
        self.card = _card(title_ru="Existing", body_ru="<p>Old</p>")

    def _form(self, **fields):
        data = {f"{field}_{lang}": "" for field in ("title", "body") for lang in ("ru", "kk", "en")}
        data.update(fields)
        return data

    def test_only_the_owner_reaches_the_card_pages(self):
        organizer = _member("organizer", User.Role.ORGANIZER)
        admin = _member("admin", User.Role.ADMIN)
        superuser = User.objects.create_superuser(username="root", email="root@test.local", password="pw")
        pages = [
            ("get", reverse("home_card_add")),
            ("get", reverse("home_card_edit", args=[self.card.pk])),
            ("post", reverse("home_card_move", args=[self.card.pk])),
            ("post", reverse("home_card_delete", args=[self.card.pk])),
        ]
        for method, url in pages:
            with self.subTest(url=url):
                self.client.logout()
                self.assertIn("login", getattr(self.client, method)(url)["Location"])
                for member in (organizer, admin, superuser):
                    self.client.force_login(member)
                    self.assertEqual(getattr(self.client, method)(url).status_code, 403)
        self.assertTrue(HomeCard.objects.filter(pk=self.card.pk).exists())

    def test_the_edit_page_lists_the_cards_in_order_with_their_actions(self):
        _card(title_ru="Added")
        self.client.force_login(self.owner)
        html = self.client.get(reverse("home_edit")).content.decode()
        self.assertLess(html.index("Existing"), html.index("Added"))
        self.assertIn(reverse("home_card_add"), html)
        self.assertIn(reverse("home_card_edit", args=[self.card.pk]), html)
        self.assertIn(reverse("home_card_delete", args=[self.card.pk]), html)

    def test_a_new_card_goes_last_and_the_owner_is_back_at_the_list(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("home_card_add"), self._form(title_ru="New", title_kk="Jana", body_ru="<p>Fresh</p>")
        )
        self.assertRedirects(response, reverse("home_edit") + "#cards", fetch_redirect_response=False)
        last = HomeCard.objects.last()
        self.assertEqual((last.title_ru, last.title_kk, last.body_ru), ("New", "Jana", "<p>Fresh</p>"))
        self.assertEqual(list(HomeCard.objects.values_list("title_ru", flat=True)), ["Existing", "New"])

    def test_a_card_is_changed_in_place(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("home_card_edit", args=[self.card.pk]), self._form(title_ru="Renamed"))
        self.card.refresh_from_db()
        self.assertEqual(self.card.title_ru, "Renamed")
        self.assertEqual(self.card.body_ru, "")

    def test_a_card_with_nothing_in_it_is_refused(self):
        self.client.force_login(self.owner)
        blank = self._form(body_ru=EMPTY_EDITOR, body_kk=EMPTY_EDITOR, body_en=EMPTY_EDITOR, title_en="   ")
        response = self.client.post(in_language(reverse("home_card_add"), "en"), blank)
        self.assertContains(response, "A card needs a heading or some text.")
        self.assertEqual(HomeCard.objects.count(), 1)

    def test_an_oversized_text_is_refused_and_shown_in_its_tab(self):
        self.client.force_login(self.owner)
        for lang in ("ru", "kk"):
            with self.subTest(lang=lang):
                fields = {"title_ru": "T", f"body_{lang}": "a" * (MAX_RICH_TEXT_LENGTH + 1)}
                response = self.client.post(in_language(reverse("home_card_add"), "en"), self._form(**fields))
                self.assertContains(response, "too large")
        self.assertEqual(HomeCard.objects.count(), 1)

    def test_a_script_sent_through_the_form_is_stripped(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("home_card_add"), self._form(body_ru="<p>safe text</p><script>alert(1)</script>"))
        self.assertNotIn("<script", HomeCard.objects.last().body_ru.lower())

    def test_a_card_is_moved_and_a_place_that_is_not_a_number_is_refused(self):
        _card(title_ru="Second")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("home_card_move", args=[self.card.pk]), {"position": "1"})
        self.assertRedirects(response, reverse("home_edit") + "#cards", fetch_redirect_response=False)
        self.assertEqual(list(HomeCard.objects.values_list("title_ru", flat=True)), ["Second", "Existing"])
        response = self.client.post(reverse("home_card_move", args=[self.card.pk]), {"position": "up"})
        self.assertEqual(response.status_code, 400)

    def test_a_card_is_deleted(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("home_card_delete", args=[self.card.pk]))
        self.assertFalse(HomeCard.objects.exists())

    def test_a_card_that_is_gone_is_not_found(self):
        self.client.force_login(self.owner)
        for name in ("home_card_edit", "home_card_move", "home_card_delete"):
            with self.subTest(page=name):
                response = self.client.post(reverse(name, args=[self.card.pk + 100]), {"position": "0"})
                self.assertEqual(response.status_code, 404)


class HomeCardsApiTests(ApiTestMixin, TestCase):
    URL = "/api/v1/home/cards/"

    def setUp(self):
        self.owner = _member("owner", User.Role.OWNER)
        self.card = _card(title_ru="Existing", body_ru="<p>Old</p>")

    def test_anyone_reads_the_cards_in_order(self):
        _card(title_ru="Second", title_en="Second EN")
        response = self.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([card["title"]["ru"] for card in data], ["Existing", "Second"])
        self.assertEqual(data[1]["title"]["en"], "Second EN")
        self.assertEqual(data[0]["body"]["ru"], "<p>Old</p>")

    def test_only_the_owner_writes(self):
        for role in (User.Role.PARTICIPANT, User.Role.ORGANIZER, User.Role.ADMIN):
            member = _member(f"m-{role}", role)
            with self.subTest(role=str(role)):
                self.assertEqual(self.post(self.URL, {"title": {"ru": "X"}}, user=member).status_code, 403)
                self.assertEqual(self.patch(f"{self.URL}{self.card.pk}", {}, user=member).status_code, 403)
                self.assertEqual(self.delete(f"{self.URL}{self.card.pk}", user=member).status_code, 403)
        self.assertEqual(self.post(self.URL, {"title": {"ru": "X"}}).status_code, 401)
        self.assertEqual(HomeCard.objects.count(), 1)

    def test_the_owner_adds_a_card_last_or_where_they_say(self):
        response = self.post(self.URL, {"title": {"ru": "Last", "kk": "Songy"}}, user=self.owner)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"]["kk"], "Songy")
        response = self.post(self.URL, {"title": {"ru": "First"}, "position": 0}, user=self.owner)
        self.assertEqual(response.json()["position"], 0)
        self.assertEqual(list(HomeCard.objects.values_list("title_ru", flat=True)), ["First", "Existing", "Last"])

    def test_the_owner_changes_moves_and_removes_a_card(self):
        _card(title_ru="Second")
        url = f"{self.URL}{self.card.pk}"
        response = self.patch(url, {"body": {"ru": "<p>New</p><script>x()</script>"}, "position": 5}, user=self.owner)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"]["ru"], "Existing")  # what was not sent stays
        self.assertNotIn("script", response.json()["body"]["ru"])
        self.assertEqual(list(HomeCard.objects.values_list("title_ru", flat=True)), ["Second", "Existing"])
        self.assertEqual(self.delete(url, user=self.owner).status_code, 204)
        self.assertEqual(self.delete(url, user=self.owner).status_code, 404)

    def test_a_position_read_is_a_position_that_keeps_the_card_where_it_is(self):
        second, third = _card(title_ru="Second"), _card(title_ru="Third")
        self.assertEqual(self.delete(f"{self.URL}{second.pk}", user=self.owner).status_code, 204)
        listed = self.get(self.URL).json()
        self.assertEqual([card["position"] for card in listed], [0, 1])
        response = self.patch(f"{self.URL}{third.pk}", {"position": listed[1]["position"]}, user=self.owner)
        self.assertEqual(response.json()["position"], 1)
        self.assertEqual(list(HomeCard.objects.values_list("title_ru", flat=True)), ["Existing", "Third"])

    def test_a_card_with_nothing_in_it_or_too_much_is_refused(self):
        refused = [
            {"title": {"ru": "  "}, "body": {"ru": EMPTY_EDITOR}},
            {"title": {"ru": "x" * 256}},
            {"title": {"ru": "T"}, "body": {"kk": "a" * (MAX_RICH_TEXT_LENGTH + 1)}},
            {"title": {"ru": "T"}, "position": -1},
        ]
        for payload in refused:
            with self.subTest(payload=str(payload)[:60]):
                self.assertEqual(self.post(self.URL, payload, user=self.owner).status_code, 422)
        response = self.patch(f"{self.URL}{self.card.pk}", {"title": {}, "body": {}}, user=self.owner)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(HomeCard.objects.count(), 1)
