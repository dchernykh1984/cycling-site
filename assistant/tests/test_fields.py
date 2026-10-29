"""The model's answer checked into form values: what passes, what is dropped, and the notes."""

from django.test import TestCase
from django.utils import translation

from assistant import fields
from assistant.tests.helpers import city, user, venue
from calendar_app.models import Discipline, DisciplineCategory, EventType
from calendar_app.views import _get_locations_data


def _check(answer, current=None, texts=(), rows=(), point=None):
    with translation.override("en"):
        return fields.check(answer, current=current or {}, texts=list(texts), rows=list(rows), point=point)


class TextTests(TestCase):
    def test_the_three_languages_are_kept_and_the_description_is_made_safe(self):
        checked = _check(
            {
                "title": {"ru": " Kofe-raid ", "kk": "Kofe-raid", "en": "Coffee ride", "de": "Kaffee"},
                "description": {"ru": "<p>Start</p><script>alert(1)</script>", "kk": "", "en": "<p>Start</p>"},
                "preview_text": "not three languages",
            }
        )
        self.assertEqual(checked.form["title_ru"], "Kofe-raid")
        self.assertNotIn("title_de", checked.form)
        self.assertEqual(checked.form["description_ru"], "<p>Start</p>")
        self.assertEqual(checked.form["description_kk"], "")
        self.assertNotIn("preview_text_ru", checked.form)
        self.assertEqual(checked.set["title"], {"ru": "Kofe-raid", "kk": "Kofe-raid", "en": "Coffee ride"})

    def test_a_text_is_cut_to_its_column(self):
        checked = _check({"title": {"ru": "x" * 300}, "preview_text": {"en": "y" * 300}})
        self.assertEqual(len(checked.form["title_ru"]), 255)
        self.assertEqual(len(checked.form["preview_text_en"]), 200)


class DateTests(TestCase):
    def test_dates_are_kept_when_they_are_dates(self):
        checked = _check({"date_start": "2026-10-31", "date_end": "31 October"})
        self.assertEqual(checked.form, {"date_start": "2026-10-31"})

    def test_an_end_before_the_start_is_emptied(self):
        self.assertEqual(_check({"date_start": "2026-11-02", "date_end": "2026-11-01"}).form["date_end"], "")
        moved = _check({"date_start": "2026-11-05"}, current={"date_start": "2026-10-31", "date_end": "2026-11-01"})
        self.assertEqual(moved.form, {"date_start": "2026-11-05", "date_end": ""})


class IdTests(TestCase):
    def test_only_ids_the_site_has_are_kept(self):
        ride = EventType.objects.create(name="Ride")
        gravel = Discipline.objects.create(name="Gravel", category=DisciplineCategory.objects.create(name="Road"))
        checked = _check({"event_type_ids": [ride.pk, 99999, "x"], "discipline_ids": [str(gravel.pk)]})
        self.assertEqual(checked.form["event_types"], [ride.pk])
        self.assertEqual(checked.form["disciplines"], [gravel.pk])


class LinkTests(TestCase):
    TEXTS = ("The track: https://www.strava.com/routes/3398 and the post t.me/ubt_club/812",)

    def test_a_link_the_administrator_wrote_is_kept_whatever_its_scheme(self):
        checked = _check(
            {"url_route": "https://strava.com/routes/3398/", "url_announcement": "https://t.me/ubt_club/812"},
            texts=self.TEXTS,
        )
        self.assertEqual(checked.form["url_route"], "https://strava.com/routes/3398/")
        self.assertEqual(checked.form["url_announcement"], "https://t.me/ubt_club/812")
        self.assertEqual(checked.notes, [])

    def test_a_link_nobody_wrote_is_dropped_with_a_note(self):
        checked = _check({"url_registration": "https://example.org/register"}, texts=self.TEXTS)
        self.assertNotIn("url_registration", checked.form)
        self.assertEqual(
            checked.notes,
            ["A link that is in neither your messages nor the form was left out: https://example.org/register"],
        )

    def test_a_link_the_form_already_holds_is_kept(self):
        current = {
            "url_route": "https://strava.com/routes/9",
            "description": {"ru": '<p>Registration: <a href="https://reg.test/42">here</a></p>', "kk": "", "en": ""},
        }
        answer = {"url_route": "https://strava.com/routes/9", "url_registration": "https://reg.test/42"}
        checked = _check(answer, current=current)
        self.assertEqual(checked.form, answer)
        self.assertEqual(checked.notes, [])

    def test_a_link_inside_a_description_must_have_been_written_too(self):
        description = (
            '<p>Track: <a href="https://strava.com/routes/3398">Strava</a>, '
            '<a href="https://made.up/page">details</a>, <a href="mailto:club@example.org">mail</a></p>'
        )
        checked = _check({"description": {"ru": description}}, texts=[*self.TEXTS, "club@example.org"])
        shown = checked.form["description_ru"]
        self.assertIn('href="https://strava.com/routes/3398"', shown)
        self.assertIn('href="mailto:club@example.org"', shown)
        self.assertIn(", details, ", shown)
        self.assertNotIn("made.up", shown)
        self.assertEqual(
            checked.notes, ["A link that is in neither your messages nor the form was left out: https://made.up/page"]
        )

    def test_an_empty_link_empties_the_field(self):
        self.assertEqual(_check({"url_route": ""}).form, {"url_route": ""})


class PlaceTests(TestCase):
    def setUp(self):
        self.town = city()
        self.shop = venue(self.town)
        self.rows = _get_locations_data(user())

    def test_a_known_venue_is_chosen_and_the_place_kept_in_the_contracts_words(self):
        answer = {"place": {"city": "Testville", "venue": {"en": "Giant shop, Abay 47"}, "junk": "x"}}
        checked = _check(answer, rows=self.rows)
        self.assertEqual(checked.form, {"location": self.shop.pk})
        self.assertEqual(
            checked.set["place"],
            {
                "country": "",
                "region": "",
                "city": "Testville",
                "venue": {"ru": "", "kk": "", "en": "Giant shop, Abay 47"},
                "lat": None,
                "lng": None,
            },
        )

    def test_typed_coordinates_count_only_when_the_administrator_wrote_them(self):
        answer = {"place": {"city": "Testville", "venue": {"ru": "Most"}, "lat": 43.21, "lng": 76.88}}
        typed = _check(answer, texts=["Start at the bridge, 43,21 76.88"], rows=self.rows)
        self.assertEqual((typed.form["new_venue"]["lat"], typed.form["new_venue"]["lng"]), (43.21, 76.88))
        made_up = _check(answer, texts=["Start at the bridge"], rows=self.rows)
        self.assertIsNone(made_up.form["new_venue"]["lat"])
        from_track = _check(answer, texts=["Start at the bridge"], rows=self.rows, point=(43.2, 76.9))
        self.assertEqual(from_track.form["new_venue"]["lat"], 43.2)

    def test_a_city_the_site_lacks_leaves_the_place_alone_with_a_note(self):
        checked = _check({"place": {"city": "Nowhereville", "venue": {"ru": "Stadion"}}}, rows=self.rows)
        self.assertEqual(checked.form, {})
        self.assertNotIn("place", checked.set)
        self.assertEqual(checked.notes, ["Nowhereville is not among the site's places: choose the place in the form."])

    def test_an_answer_that_is_not_an_object_changes_nothing(self):
        checked = _check(["not", "an", "object"])
        self.assertEqual((checked.set, checked.form, checked.notes), ({}, {}, []))


class NewsTests(TestCase):
    def test_a_news_answer_sets_its_texts_and_nothing_an_event_has(self):
        answer = {
            "title": {"kk": " Zhanalyq "},
            "intro": {"en": "x" * 600},
            "body": {"en": '<p>Text</p><img src="image:1"><script>x</script>'},
            "date_start": "2026-11-01",
            "url_route": "https://example.org/r",
        }
        checked = fields.check(
            answer, kind="news", current={}, texts=[], rows=[], images=['<img src="https://example.org/a.png">']
        )
        self.assertEqual(set(checked.form), {"title_kk", "intro_en", "body_en"})
        self.assertEqual(checked.form["title_kk"], "Zhanalyq")
        self.assertEqual(len(checked.form["intro_en"]), 500)
        self.assertIn('src="https://example.org/a.png"', checked.form["body_en"])
        self.assertNotIn("script", checked.form["body_en"])
        self.assertEqual(checked.notes, [])
