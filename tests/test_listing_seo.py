"""A filtered competition list, as a search result shows it.

The URL `/calendar/list/?location=2` has always returned the right events as plain HTML; what it
never had was any sign of what it holds. Every filter combination carried the same title and the
same site-wide description, so instead of a page per city and per discipline there was one page
repeated. "Races in Almaty" is what people type; this is what answers it.
"""

import datetime
import re

from django.test import TestCase
from django.urls import reverse

from calendar_app.models import Competition, Discipline, DisciplineCategory
from locations.models import add_location_child
from tests.language_urls import in_language

FIRST = datetime.date.today() + datetime.timedelta(days=5)
SPAN = {"date_from": FIRST.isoformat(), "date_to": (FIRST + datetime.timedelta(days=40)).isoformat()}


def _title(html):
    return re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", html, re.S).group(1)).strip()


def _description(html):
    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else ""


class FilteredListMetaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan", name_en="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty", name_en="Almaty")
        venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        category = DisciplineCategory.objects.create(name_ru="Road", name_en="Road", order=1)
        cls.discipline = Discipline.objects.create(name_ru="Criterium", name_en="Criterium", category=category, order=1)
        comp = Competition.objects.create(
            title_ru="City race", date_start=FIRST, status=Competition.Status.APPROVED, location=venue
        )
        comp.disciplines.set([cls.discipline])

    def _get(self, **params):
        return self.client.get(
            in_language(reverse("calendar_list"), "en"), {**SPAN, **params}, HTTP_ACCEPT_LANGUAGE="en"
        ).content.decode()

    def test_a_city_filter_names_the_city_in_the_title(self):
        self.assertIn("Almaty", _title(self._get(location=self.city.pk)))

    def test_a_discipline_filter_names_the_discipline(self):
        self.assertIn("Criterium", _title(self._get(discipline=self.discipline.pk)))

    def test_the_description_says_how_many_events_there_are(self):
        description = _description(self._get(location=self.city.pk))
        self.assertIn("Almaty", description)
        self.assertRegex(description, r"\d+")

    def test_two_filters_do_not_share_a_description(self):
        by_city = _description(self._get(location=self.city.pk))
        by_discipline = _description(self._get(discipline=self.discipline.pk))
        self.assertNotEqual(by_city, by_discipline)

    def test_an_unfiltered_list_keeps_the_site_wide_text(self):
        """Nothing of its own to say, so it must not invent something."""
        self.assertNotIn("Almaty", _title(self._get()))


class LandingFacetsTests(TestCase):
    """Which cities and disciplines are worth offering as a page of their own.

    The block under the calendar is what a reader and a crawler both walk into the calendar
    through, and it used to carry two kinds of entry nobody searches for: the tree's catch-all city
    and each category's leftovers bin.
    """

    @classmethod
    def setUpTestData(cls):
        from calendar_app.models import Competition
        from locations.models import Location, add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(country.get_children()[0], name="Almaty", name_ru="Almaty")
        cls.other_city = add_location_child(
            region, name="Other city", name_ru="Other city", name_en="Other city", is_hidden=True
        )
        venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        other_venue = add_location_child(cls.other_city, name="Somewhere", name_ru="Somewhere")

        category = DisciplineCategory.objects.create(name="Road", name_ru="Road", name_en="Road")
        cls.real = Discipline.objects.create(
            name="Road race", name_ru="Road race", name_en="Road race", category=category
        )
        cls.bin = Discipline.objects.create(
            name="Other (Road Cycling)",
            name_ru="Drugoe",
            name_en="Other (Road Cycling)",
            category=category,
        )
        for location, discipline in ((venue, cls.real), (other_venue, cls.bin)):
            comp = Competition.objects.create(
                title_ru="Race",
                date_start=datetime.date.today() + datetime.timedelta(days=10),
                status=Competition.Status.APPROVED,
                location=location,
            )
            comp.disciplines.add(discipline)
        cls.Location = Location

    def _facets(self):
        from calendar_app.listing_seo import landing_filters

        _regions, places, kinds = landing_filters()
        return [p.pk for p in places], [k.pk for k in kinds]

    def test_the_catch_all_city_is_not_offered_as_a_place(self):
        places, _kinds = self._facets()
        self.assertIn(self.city.pk, places)
        self.assertNotIn(self.other_city.pk, places)

    def test_a_categorys_leftovers_bin_is_not_offered_as_a_discipline(self):
        _places, kinds = self._facets()
        self.assertIn(self.real.pk, kinds)
        self.assertNotIn(self.bin.pk, kinds)

    def test_the_calendar_page_offers_neither(self):
        response = self.client.get(reverse("calendar"))
        html = response.content.decode()
        self.assertIn(f"location={self.city.pk}", html)
        self.assertNotIn(f"location={self.other_city.pk}", html)
        self.assertNotIn(f"discipline={self.bin.pk}", html)

    def test_every_leftovers_bin_the_catalogue_holds_is_recognised(self):
        """The marker is the English name, so a renamed bin would slip back into the block."""
        from calendar_app.listing_seo import CATCH_ALL_DISCIPLINE_PREFIX

        bins = Discipline.objects.filter(name_en__startswith=CATCH_ALL_DISCIPLINE_PREFIX)
        self.assertIn(self.bin, bins)
        for discipline in Discipline.objects.exclude(pk__in=bins.values("pk")):
            self.assertFalse(
                (discipline.name_en or "").startswith("Other "),
                f"{discipline.name_en} looks like a bin but is not matched",
            )


class FilteredHeadingTests(TestCase):
    """The heading of a filtered list says what it is filtered by.

    Every one of the hundred filter pages in the sitemap carried the same h1 -- "Competitions" --
    so the page a reader landed on from search never named the thing they had searched for.
    """

    @classmethod
    def setUpTestData(cls):
        from locations.models import add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        Competition.objects.create(
            title_ru="Race",
            date_start=datetime.date.today() + datetime.timedelta(days=10),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def _h1(self, url):
        html = self.client.get(url).content.decode()
        return re.sub(r"\s+", " ", re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)).strip()

    def test_a_place_names_itself_in_the_heading(self):
        heading = self._h1(f"{reverse('calendar_list')}?location={self.city.pk}")
        self.assertIn("Almaty", heading)

    def test_the_unfiltered_list_keeps_the_plain_word(self):
        from django.utils import translation

        with translation.override("ru"):
            plain = translation.gettext("Competitions")
        self.assertEqual(self._h1(reverse("calendar_list")), plain)

    def test_the_heading_matches_the_title_tag(self):
        html = self.client.get(f"{reverse('calendar_list')}?location={self.city.pk}").content.decode()
        heading = re.sub(r"\s+", " ", re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)).strip()
        self.assertIn(heading, _title(html))


class FacetedListSpanTests(TestCase):
    """How far ahead a filtered list looks.

    The plain list is a "what is on soon" page and stops thirty days out. A page about one city
    cannot: on production the Almaty page showed two events, which is not a page about Almaty.
    """

    @classmethod
    def setUpTestData(cls):
        from locations.models import add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(cls.city, name="Republic Square", name_ru="Republic Square")
        today = datetime.date.today()
        cls.soon = Competition.objects.create(
            title_ru="Soon race",
            date_start=today + datetime.timedelta(days=10),
            status=Competition.Status.APPROVED,
            location=venue,
        )
        cls.autumn = Competition.objects.create(
            title_ru="Autumn race",
            date_start=today + datetime.timedelta(days=120),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def _rows(self, url):
        return [c.pk for c in self.client.get(url).context["competitions"]]

    def test_a_city_page_reaches_past_the_next_month(self):
        rows = self._rows(f"{reverse('calendar_list')}?location={self.city.pk}")
        self.assertIn(self.soon.pk, rows)
        self.assertIn(self.autumn.pk, rows)

    def test_the_plain_list_still_stops_at_thirty_days(self):
        rows = self._rows(reverse("calendar_list"))
        self.assertIn(self.soon.pk, rows)
        self.assertNotIn(self.autumn.pk, rows)

    def test_a_date_the_reader_asked_for_still_wins(self):
        end = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
        rows = self._rows(f"{reverse('calendar_list')}?location={self.city.pk}&date_to={end}")
        self.assertIn(self.soon.pk, rows)
        self.assertNotIn(self.autumn.pk, rows)

    def test_a_city_page_does_not_claim_a_date_range_it_no_longer_has(self):
        html = self.client.get(f"{reverse('calendar_list')}?location={self.city.pk}").content.decode()
        self.assertNotIn(" to ", _description(html))

    def test_the_open_end_leaves_the_date_field_empty_rather_than_saying_none(self):
        """The upper bound is gone, not set to the word Python prints for nothing."""
        html = self.client.get(f"{reverse('calendar_list')}?location={self.city.pk}").content.decode()
        field = re.search(r'<input[^>]+name="date_to"[^>]*>', html).group(0)
        self.assertIn('value=""', field)
        self.assertNotIn("None", field)


class RegionFacetTests(TestCase):
    """Regions as pages of their own.

    A start at a village called Kyrbaltabay is invisible to anyone typing "races near Almaty". The
    region page gathers that village with the towns around it into the page that answers the
    question people actually ask.
    """

    @classmethod
    def setUpTestData(cls):
        from locations.models import add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        cls.region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        cls.empty_region = add_location_child(country, name="Empty region", name_ru="Empty region")
        village = add_location_child(cls.region, name="Kyrbaltabay", name_ru="Kyrbaltabay")
        venue = add_location_child(village, name="UBT TT", name_ru="UBT TT")
        cls.comp = Competition.objects.create(
            title_ru="Time trial",
            date_start=datetime.date.today() + datetime.timedelta(days=20),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def test_a_region_holding_events_is_offered(self):
        from calendar_app.listing_seo import landing_filters

        regions, _places, _kinds = landing_filters()
        self.assertIn(self.region.pk, [r.pk for r in regions])
        self.assertNotIn(self.empty_region.pk, [r.pk for r in regions])

    def test_the_calendar_links_the_region(self):
        html = self.client.get(reverse("calendar")).content.decode()
        self.assertIn(f"location={self.region.pk}", html)

    def test_the_region_page_gathers_the_villages_below_it(self):
        response = self.client.get(f"{reverse('calendar_list')}?location={self.region.pk}")
        self.assertIn(self.comp.pk, [c.pk for c in response.context["competitions"]])
        self.assertIn("Almaty region", _title(response.content.decode()))

    def test_the_region_reaches_the_sitemap(self):
        html = self.client.get("/sitemap-calendar-filters.xml").content.decode()
        self.assertIn(f"location={self.region.pk}", html)


class EmptyFilterValueTests(TestCase):
    """A parameter with nothing in it is not a filter.

    A cleared select and a stale link both send "?location=", which is no id at all. Read as a
    filter it emptied the page -- every event excluded by an empty set of places -- and told the
    view it was looking at a landing page.
    """

    @classmethod
    def setUpTestData(cls):
        from locations.models import add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty region", name_ru="Almaty region")
        city = add_location_child(region, name="Almaty", name_ru="Almaty")
        venue = add_location_child(city, name="Republic Square", name_ru="Republic Square")
        today = datetime.date.today()
        cls.soon = Competition.objects.create(
            title_ru="Soon race",
            date_start=today + datetime.timedelta(days=10),
            status=Competition.Status.APPROVED,
            location=venue,
        )
        cls.autumn = Competition.objects.create(
            title_ru="Autumn race",
            date_start=today + datetime.timedelta(days=120),
            status=Competition.Status.APPROVED,
            location=venue,
        )

    def _rows(self, url):
        return [c.pk for c in self.client.get(url).context["competitions"]]

    def test_an_empty_place_still_lists_the_events(self):
        self.assertIn(self.soon.pk, self._rows(f"{reverse('calendar_list')}?location="))

    def test_an_empty_place_is_not_taken_for_a_landing_page(self):
        """No filter means the plain list, which stops thirty days out."""
        self.assertNotIn(self.autumn.pk, self._rows(f"{reverse('calendar_list')}?location="))

    def test_junk_in_the_parameter_is_ignored_the_same_way(self):
        rows = self._rows(f"{reverse('calendar_list')}?location=abc&discipline=")
        self.assertIn(self.soon.pk, rows)
        self.assertNotIn(self.autumn.pk, rows)
