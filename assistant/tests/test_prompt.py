"""What the model is told: the system part, the form in words, the turn and the conversation."""

import datetime
import json

from django.test import TestCase

from assistant import prompt
from assistant.models import Conversation, Message
from assistant.tests.helpers import city, competition, user, venue
from calendar_app.models import Discipline, DisciplineCategory, EventType


class SystemPromptTests(TestCase):
    def setUp(self):
        self.ride = EventType.objects.create(name_ru="Zaezd", name_en="Ride", order=1)
        road = DisciplineCategory.objects.create(name_ru="Shosse", name_en="Road")
        self.gravel = Discipline.objects.create(name_ru="Grevel", name_en="Gravel", category=road)

    def test_it_holds_the_contract_every_skill_and_the_lists_with_their_ids(self):
        text = prompt.system_prompt()
        self.assertIn(prompt.CONTRACT, text)
        skills = sorted((prompt.SKILLS_DIR / "event").glob("*.md"))
        self.assertTrue(skills)
        for path in skills:
            self.assertIn(path.read_text(encoding="utf-8").strip(), text)
        self.assertIn(f"{self.ride.pk}: Zaezd / Ride", text)
        self.assertIn(f"  {self.gravel.pk}: Grevel / Gravel", text)

    def test_it_reads_the_same_on_every_turn(self):
        self.assertEqual(prompt.system_prompt(), prompt.system_prompt())

    def test_the_lists_take_three_queries_however_many_directions(self):
        for name in ("Trail", "Track"):
            DisciplineCategory.objects.create(name_ru=name, name_en=name)
        with self.assertNumQueries(3):
            prompt.taxonomy()


class DescribeFormTests(TestCase):
    def test_a_chosen_venue_is_named_by_its_whole_path(self):
        spot = venue()
        form = prompt.describe_form({"location": str(spot.pk)})
        self.assertEqual(form["place"], "Testland / Test Region / Testville / Giant shop, Abay 47")

    def test_a_city_without_its_spot_says_so(self):
        town = city()
        catch_all = town.get_children().get(is_hidden=True)
        form = prompt.describe_form({"location": str(catch_all.pk)})
        self.assertEqual(form["place"], "Testland / Test Region / Testville (the exact spot not chosen)")

    def test_a_new_venue_carries_its_names_city_and_point(self):
        town = city()
        raw = {
            "new_venue_city": str(town.pk),
            "new_venue_name": "Vkhod v park",
            "new_venue_name_en": "Park entrance",
            "new_venue_lat": "43.2",
            "new_venue_lng": "",
        }
        place = prompt.describe_form(raw)["place"]
        self.assertEqual(place["new_venue"], {"ru": "Vkhod v park", "kk": "", "en": "Park entrance"})
        self.assertEqual(place["city"], "Testland / Test Region / Testville")
        self.assertIsNone(place["point"])

    def test_what_the_page_sent_is_bounded_and_typed(self):
        raw = {
            "title_ru": "  Ride  ",
            "title_kk": "x" * 400,
            "event_types": ["3", "x", 4],
            "disciplines": "7",
            "registration_enabled": "true",
            "url_route": ["not", "a", "string"],
        }
        form = prompt.describe_form(raw)
        self.assertEqual(form["title"]["ru"], "Ride")
        self.assertEqual(len(form["title"]["kk"]), 255)
        self.assertEqual(form["event_type_ids"], [3, 4])
        self.assertEqual(form["discipline_ids"], [])
        self.assertFalse(form["registration_on_the_site"])
        self.assertEqual(form["url_route"], "")
        self.assertEqual(prompt.describe_form(None)["place"], "")

    def test_a_long_description_goes_whole_so_a_rewrite_cannot_drop_its_end(self):
        long_text = "<p>" + "x" * 30_000 + "</p>"
        self.assertEqual(prompt.describe_form({"description_ru": long_text})["description"]["ru"], long_text)
        self.assertEqual(prompt.describe_news({"body_en": long_text})["body"]["en"], long_text)

    def test_an_edited_events_stored_file_counts_as_attached(self):
        event = competition(file_route="competitions/routes/coffee-ride.gpx")
        form = prompt.describe_form({}, event)
        self.assertEqual(form["files"]["route"], "coffee-ride.gpx")
        self.assertEqual(prompt.describe_form({"file_route": "new.gpx"}, event)["files"]["route"], "new.gpx")


class TurnTests(TestCase):
    def test_a_turn_names_the_day_the_page_the_form_and_the_files_before_the_words(self):
        text = prompt.turn(
            "Saturday ride",
            {"date_start": ""},
            [{"kind": "route", "name": "ride.gpx", "start": [43.2389, 76.9453]}],
            datetime.date(2026, 10, 29),
            "kk",
            editing=False,
        )
        self.assertIn("Today is 2026-10-29, Thursday. The page's language: kk.", text)
        self.assertIn("adding a new event", text)
        self.assertIn('The form now: {"date_start": ""}', text)
        self.assertIn(
            '"ride.gpx"; it is in the form as the route file. The track starts at 43.238900, 76.945300.', text
        )
        self.assertTrue(text.endswith("The administrator writes:\nSaturday ride"))
        self.assertIn("editing an event", prompt.turn("x", {}, [], datetime.date(2026, 10, 29), "ru", editing=True))


class MessagesTests(TestCase):
    def test_the_conversation_comes_between_the_system_part_and_the_turn(self):
        conversation = Conversation.objects.create(started_by=user())
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            text="rules.pdf",
            attachments=[{"kind": "regulations", "name": "rules.pdf", "start": None}],
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            text="Got the regulations.",
            fields={"url_route": "https://example.test/route"},
        )
        sent = prompt.messages(conversation, "This turn")
        self.assertEqual([m["role"] for m in sent], ["system", "user", "assistant", "user"])
        self.assertIn("it is in the form as the regulations file", sent[1]["content"])
        self.assertEqual(
            json.loads(sent[2]["content"]),
            {"reply": "Got the regulations.", "set": {"url_route": "https://example.test/route"}},
        )
        self.assertEqual(sent[3]["content"], "This turn")


class NewsPromptTests(TestCase):
    def test_a_news_conversation_gets_the_news_contract_and_skill_and_nothing_of_events(self):
        text = prompt.system_prompt("news")
        self.assertIn(prompt.NEWS_CONTRACT, text)
        for path in sorted((prompt.SKILLS_DIR / "news").glob("*.md")):
            self.assertIn(path.read_text(encoding="utf-8").strip(), text)
        for path in sorted((prompt.SKILLS_DIR / "event").glob("*.md")):
            self.assertNotIn(path.read_text(encoding="utf-8").strip(), text)
        self.assertNotIn("Disciplines", text)

    def test_a_news_form_is_its_headline_short_description_and_text(self):
        images: list[str] = []
        raw = {"title_ru": "Novost", "intro_en": "Short", "body_ru": '<p>A</p><img src="https://example.org/a.png">'}
        form = prompt.describe_news(raw, images)
        self.assertEqual(set(form), {"title", "intro", "body"})
        self.assertEqual(form["body"]["ru"], '<p>A</p><img src="image:1">')
        self.assertEqual(images, ['<img src="https://example.org/a.png">'])
        self.assertIn(
            "writing a new news item",
            prompt.turn("x", form, [], datetime.date(2026, 10, 29), "ru", editing=False, kind="news"),
        )
