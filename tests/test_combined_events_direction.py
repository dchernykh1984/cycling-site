"""All-round competitions have a direction of their own, general physical preparation first (migration 0041).

The migration's functions are called against the real app registry rather than driven through
MigrationExecutor, for the reason HikingMigrationTests gives: rolling the app back in-process
truncates the seeded tables for every test that runs afterwards. A TestCase rolls each write here
back. Assertions use the English names, so this file stays ASCII.
"""

import datetime
import importlib

from django.apps import apps as registry
from django.test import TestCase
from django.utils import translation

from calendar_app.models import Competition, Discipline, DisciplineCategory

DIRECTION = "Combined Events"
KINDS = [
    "General Physical Preparation (GPP)",
    "Athletics Combined Events",
    "Polyathlon",
    "Modern Pentathlon",
    "Other (Combined Events)",
]


def migration():
    return importlib.import_module("calendar_app.migrations.0041_add_combined_events_category")


class CombinedEventsDirectionTests(TestCase):
    def direction(self):
        return DisciplineCategory.objects.get(name_en=DIRECTION)

    def test_the_direction_offers_its_kinds_with_general_physical_preparation_first(self):
        kinds = self.direction().disciplines.order_by("order").values_list("name_en", flat=True)
        self.assertEqual(list(kinds), KINDS)

    def test_it_comes_after_the_directions_there_were_so_none_of_them_moves(self):
        self.assertGreater(self.direction().order, DisciplineCategory.objects.get(name_en="Hiking").order)

    def test_every_name_is_given_in_all_three_languages(self):
        direction = self.direction()
        for item in [direction, *direction.disciplines.all()]:
            self.assertTrue(item.name_ru and item.name_kk and item.name_en, f"{item.name_en} misses a locale")
            self.assertNotEqual(item.name_ru, item.name_en, f"{item.name_en} copies another language")

    def test_an_event_in_the_catch_all_reads_as_its_direction(self):
        catch_all = self.direction().disciplines.get(name_en="Other (Combined Events)")
        event = Competition.objects.create(title="All-round", date_start=datetime.date(2027, 5, 15))
        event.disciplines.add(catch_all)
        with translation.override("en"):
            self.assertIn("Disciplines: Combined Events.", event.search_summary())

    def test_the_api_the_agents_read_lists_it_in_every_language(self):
        listed = next(c for c in self.client.get("/api/v1/disciplines/").json() if c["name"]["en"] == DIRECTION)
        self.assertTrue(listed["name"]["ru"] and listed["name"]["kk"])
        self.assertEqual([d["name"]["en"] for d in listed["disciplines"]], KINDS)
        for discipline in listed["disciplines"]:
            for locale in ("ru", "kk", "en"):
                self.assertTrue(discipline["name"][locale], f"{discipline['name']} misses {locale}")

    def test_seeding_again_duplicates_nothing(self):
        """Migrations get replayed on restored backups, so a second run must be a no-op."""
        migration().add_combined_events(registry, None)
        self.assertEqual(DisciplineCategory.objects.filter(name_en=DIRECTION).count(), 1)
        self.assertEqual(Discipline.objects.filter(category__name_en=DIRECTION).count(), len(KINDS))

    def test_the_reverse_refuses_to_drop_a_discipline_an_event_uses(self):
        """This guard is the only thing between a rollback and an event losing its discipline."""
        gpp = self.direction().disciplines.get(name_en=KINDS[0])
        event = Competition.objects.create(title="GPP", date_start=datetime.date(2027, 5, 15))
        event.disciplines.add(gpp)
        with self.assertRaises(RuntimeError):
            migration().remove_combined_events(registry, None)
        self.assertEqual(list(event.disciplines.values_list("pk", flat=True)), [gpp.pk])
        self.assertEqual(Discipline.objects.filter(category__name_en=DIRECTION).count(), len(KINDS))

    def test_the_reverse_removes_the_direction_when_nothing_uses_it(self):
        migration().remove_combined_events(registry, None)
        self.assertFalse(DisciplineCategory.objects.filter(name_en=DIRECTION).exists())
        self.assertFalse(Discipline.objects.filter(name_en__in=KINDS).exists())
