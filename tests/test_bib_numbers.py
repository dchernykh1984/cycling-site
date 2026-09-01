"""Start numbers, and the promise that no two riders share one.

An organizer writes the men's categories as 61-120 each, meaning "the men are that block". Every
category used to start counting at its own bib_from, so both men's groups began at 61 and eight
riders carried a number somebody else also carried.
"""

import datetime

from django.test import TestCase

from calendar_app.models import Competition
from registrations.models import CompetitionRegistration, RegistrationCategory
from registrations.views import build_participant_groups

TODAY = datetime.date.today()


def _competition(**kwargs):
    defaults = {
        "title_ru": "Race",
        "date_start": TODAY + datetime.timedelta(days=7),
        "status": Competition.Status.APPROVED,
        "registration_enabled": True,
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


class BibNumberTests(TestCase):
    def setUp(self):
        self.competition = _competition()
        self._riders = 0

    def _category(self, name, order, **kwargs):
        return RegistrationCategory.objects.create(competition=self.competition, name=name, order=order, **kwargs)

    def _rider(self, category, **kwargs):
        self._riders += 1
        defaults = {
            "competition": self.competition,
            "category": category,
            "first_name": f"R{self._riders}",
            "last_name": f"L{self._riders}",
            "gender": "M",
            "birth_date": datetime.date(1990, 1, 1),
        }
        defaults.update(kwargs)
        return CompetitionRegistration.objects.create(**defaults)

    def _numbers(self, registrations, categories, counts=None):
        groups = build_participant_groups(registrations, categories, counts=counts)
        return [[number for number, _row in group["rows"]] for group in groups]

    def test_two_categories_sharing_a_range_do_not_share_numbers(self):
        """The reported bug: both men's groups were written 61-120 and both started at 61."""
        first = self._category("Men 2011-1991", 1, bib_from=61, bib_to=120)
        second = self._category("Men 1990-1981", 2, bib_from=61, bib_to=120)
        riders = [self._rider(first) for _ in range(3)] + [self._rider(second) for _ in range(2)]
        self.assertEqual(self._numbers(riders, [first, second]), [[61, 62, 63], [64, 65]])

    def test_the_first_of_the_overlapping_categories_takes_the_low_numbers(self):
        first = self._category("A", 1, bib_from=61)
        second = self._category("B", 2, bib_from=61)
        riders = [self._rider(first), self._rider(second)]
        self.assertEqual(self._numbers(riders, [first, second]), [[61], [62]])

    def test_a_range_of_its_own_still_starts_where_it_says(self):
        """Nothing is pushed along when there is no collision to avoid."""
        women = self._category("Women", 1, bib_from=1, bib_to=60)
        men = self._category("Men", 2, bib_from=61, bib_to=120)
        riders = [self._rider(women), self._rider(men)]
        self.assertEqual(self._numbers(riders, [women, men]), [[1], [61]])

    def test_a_lower_range_after_a_higher_one_keeps_its_own_numbers(self):
        high = self._category("High", 1, bib_from=100)
        low = self._category("Low", 2, bib_from=1)
        riders = [self._rider(high), self._rider(high), self._rider(low)]
        self.assertEqual(self._numbers(riders, [high, low]), [[100, 101], [1]])

    def test_a_partial_overlap_only_skips_what_is_taken(self):
        first = self._category("First", 1, bib_from=1)
        second = self._category("Second", 2, bib_from=3)
        riders = [self._rider(first) for _ in range(4)] + [self._rider(second) for _ in range(2)]
        self.assertEqual(self._numbers(riders, [first, second]), [[1, 2, 3, 4], [5, 6]])

    def test_every_number_in_the_event_is_unique(self):
        categories = [self._category(f"C{i}", i, bib_from=61) for i in range(1, 5)]
        riders = [self._rider(category) for category in categories for _ in range(3)]
        numbers = [n for group in self._numbers(riders, categories) for n in group]
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(sorted(numbers), list(range(61, 61 + len(numbers))))

    def test_riders_without_a_category_do_not_reuse_numbers_either(self):
        category = self._category("A", 1, bib_from=1)
        riders = [self._rider(category), self._rider(None), self._rider(None)]
        self.assertEqual(self._numbers(riders, [category]), [[1], [2, 3]])

    def test_a_rider_who_does_not_count_consumes_no_number(self):
        first = self._category("A", 1, bib_from=61)
        second = self._category("B", 2, bib_from=61)
        kept = self._rider(first)
        rejected = self._rider(first, is_rejected=True)
        following = self._rider(second)
        numbers = self._numbers([kept, rejected, following], [first, second], counts=lambda reg: not reg.is_rejected)
        self.assertEqual(numbers, [[61, None], [62]])

    def test_an_empty_category_reserves_nothing(self):
        """A number belongs to a rider, not to a section: an empty group must not push others."""
        empty = self._category("Empty", 1, bib_from=61)
        used = self._category("Used", 2, bib_from=61)
        rider = self._rider(used)
        self.assertEqual(self._numbers([rider], [empty, used]), [[61]])
