"""Saving the calendar filter into the member's preferences (issue #322).

A button in the filter saves it on request; a tick in the profile saves it on every change instead,
and then the button is not shown. Event types are kept like the rest of the filter now, so a fresh
visit opens with them too. Dates and "only favourites" are not preferences and are not saved.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Discipline, DisciplineCategory, EventType
from locations.models import add_location_child

SAVE = reverse("account_save_filters")


class _Member(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="rider", email="rider@example.com", password="pw", role=User.Role.PARTICIPANT
        )
        cls.race = EventType.objects.get(name_en="Race")
        cls.training = EventType.objects.get(name_en="Kids Race")
        cls.road = DisciplineCategory.objects.create(name_ru="Road", order=1)
        cls.crit = Discipline.objects.create(name_ru="Criterium", category=cls.road, order=1)
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        cls.almaty = add_location_child(country, name="Almaty", name_ru="Almaty")

    def setUp(self):
        self.client.force_login(self.user)

    def save(self, scope, **lists):
        data = {"scope": ",".join(scope)}
        data.update({name: ",".join(str(v) for v in values) for name, values in lists.items()})
        return self.client.post(SAVE, data)


class SaveEndpointTests(_Member):
    def test_everything_the_page_has_is_saved(self):
        response = self.save(
            ["event_type", "direction", "location"],
            event_type=[self.race.pk, self.training.pk],
            discipline_category=[self.road.pk],
            discipline=[self.crit.pk],
            location=[self.almaty.pk],
        )
        self.assertEqual(response.json(), {"saved": True})
        self.assertEqual(set(self.user.preferred_event_types.all()), {self.race, self.training})
        self.assertEqual(list(self.user.preferred_directions.all()), [self.road])
        self.assertEqual(list(self.user.preferred_disciplines.all()), [self.crit])
        self.assertEqual(list(self.user.preferred_locations.all()), [self.almaty])

    def test_a_filter_the_page_does_not_have_is_left_alone(self):
        """The map has no location filter: saving from it must not wipe the saved places."""
        self.user.preferred_locations.add(self.almaty)
        self.save(["event_type", "direction"], event_type=[self.race.pk])
        self.assertEqual(list(self.user.preferred_locations.all()), [self.almaty])

    def test_an_emptied_filter_is_saved_empty(self):
        self.user.preferred_event_types.add(self.race)
        self.save(["event_type"])
        self.assertFalse(self.user.preferred_event_types.exists())

    def test_junk_and_unknown_ids_are_dropped(self):
        self.save(["event_type"], event_type=["abc", 999999, self.race.pk])
        self.assertEqual(list(self.user.preferred_event_types.all()), [self.race])

    def test_only_a_signed_in_member_can_save(self):
        self.client.logout()
        response = self.save(["event_type"], event_type=[self.race.pk])
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])

    def test_one_save_costs_a_handful_of_queries(self):
        """The issue asks whether saving on every change loads the site: it is one small write each."""
        with CaptureQueriesContext(connection) as ctx:
            self.save(
                ["event_type", "direction", "location"],
                event_type=[self.race.pk],
                discipline_category=[self.road.pk],
                discipline=[self.crit.pk],
                location=[self.almaty.pk],
            )
        self.assertLessEqual(len(ctx.captured_queries), 15, [q["sql"] for q in ctx.captured_queries])


class FreshVisitTests(_Member):
    def test_saved_event_types_open_with_the_calendar(self):
        self.user.preferred_event_types.add(self.race)
        response = self.client.get(reverse("calendar_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"event_type={self.race.pk}", response["Location"])

    def test_event_types_alone_count_as_preferences_for_the_setup_hint(self):
        self.user.preferred_event_types.add(self.race)
        response = self.client.get(reverse("calendar_list"), follow=True)
        hint = response.context.get("setup_hint") or {}
        self.assertNotEqual(hint.get("key"), "preferences")


class ProfileTests(_Member):
    def test_the_profile_saves_event_types_and_the_autosave_tick(self):
        self.client.post(
            reverse("account_profile_edit"),
            {"preferred_event_types": [self.race.pk], "autosave_filters": "on"},
        )
        self.user.refresh_from_db()
        self.assertEqual(list(self.user.preferred_event_types.all()), [self.race])
        self.assertTrue(self.user.autosave_filters)


class FilterButtonTests(_Member):
    PAGES = ("calendar", "calendar_list", "calendar_map")

    def _page(self, name):
        return self.client.get(reverse(name), {"reset": "1"})

    def test_the_button_is_on_every_calendar_page(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                self.assertContains(self._page(name), 'id="save-filter-btn"')

    def test_no_button_and_saving_on_change_when_always_save_is_on(self):
        self.user.autosave_filters = True
        self.user.save(update_fields=["autosave_filters"])
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self._page(name)
                self.assertNotContains(response, 'id="save-filter-btn"')
                self.assertContains(response, "window.saveFilterToPreferences();")

    def test_nothing_for_a_visitor(self):
        self.client.logout()
        for name in self.PAGES:
            with self.subTest(page=name):
                self.assertNotContains(self._page(name), "saveFilterToPreferences")


class TranslationTests(TestCase):
    MSGIDS = (
        "Preferred event types",
        "Always save the calendar filter into these preferences",
        "Every change you make to the filter on the calendar, list or map is kept here, and the calendar opens "
        "with it next time.",
        "Save filter to my preferences",
        "Saved to your preferences",
        "The calendar, list and map open with these filters. A field left at 'All' narrows nothing.",
    )

    def test_every_new_string_is_translated(self):
        from django.utils.translation import gettext, override

        for msgid in self.MSGIDS:
            for lang in ("ru", "kk"):
                with self.subTest(msgid=msgid[:30], lang=lang), override(lang):
                    self.assertNotEqual(gettext(msgid), msgid)
