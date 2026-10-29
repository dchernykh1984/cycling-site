"""Places' Kazakh names and English letters, as migration 0018 puts them right.

The names themselves are Cyrillic and the source ASCII-only, so they are taken from the migration.
"""

import importlib

from django.apps import apps
from django.test import TestCase

from locations.models import Location

names = importlib.import_module("locations.migrations.0018_kazakh_names_and_latin_english")


class SeededCountriesTests(TestCase):
    def test_every_seeded_country_it_names_reads_in_kazakh(self):
        seeded = Location.objects.filter(depth=1, name_ru__in=list(names.COUNTRIES))
        self.assertTrue(seeded.exists())
        for node in seeded:
            with self.subTest(country=node.name_en):
                self.assertEqual(node.name_kk, names.COUNTRIES[node.name_ru])


class NameThemTests(TestCase):
    def setUp(self):
        self.russian, self.kazakh = next(iter(names.COUNTRIES.items()))
        self.country = Location.objects.filter(depth=1, name_ru=self.russian).first()

    def test_a_name_a_person_wrote_is_left_alone(self):
        self.country.name_kk = "Written by hand"
        self.country.save()
        names.name_them(apps, None)
        self.country.refresh_from_db()
        self.assertEqual(self.country.name_kk, "Written by hand")
        self.country.name_kk = self.country.name_ru
        self.country.save()
        names.name_them(apps, None)
        self.country.refresh_from_db()
        self.assertEqual(self.country.name_kk, self.kazakh)

    def test_a_region_is_named_under_its_own_country_only(self):
        (country_name, region_name), kazakh = next(iter(names.REGIONS.items()))
        country = Location.objects.filter(depth=1, name_ru=country_name).first()
        region = country.add_child(name_ru=region_name, name_kk=region_name, name_en="Region")
        namesake = Location.add_root(name_ru="Testland", name_en="Testland").add_child(
            name_ru=region_name, name_kk=region_name, name_en="Region"
        )
        names.name_them(apps, None)
        region.refresh_from_db()
        namesake.refresh_from_db()
        self.assertEqual(region.name_kk, kazakh)
        self.assertEqual(namesake.name_kk, region_name)

    def test_an_english_name_in_cyrillic_is_written_in_latin_letters(self):
        (_country, region_name), _kazakh = next(iter(names.REGIONS.items()))
        place = Location.add_root(name_ru=region_name, name_kk=region_name, name_en=region_name)
        names.name_them(apps, None)
        place.refresh_from_db()
        self.assertTrue(place.name_en.isascii())
        self.assertEqual(place.name_en, names.in_latin(region_name))
