"""Unit tests for Competition.location_label and the list-view location filter."""

import datetime

import pytest
from django.test import Client

from calendar_app.models import Competition
from locations.models import Location

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_TODAY = datetime.date.today()
_DATE = _TODAY + datetime.timedelta(days=7)
_DATE_FROM = _TODAY.isoformat()
_DATE_TO = (_TODAY + datetime.timedelta(days=30)).isoformat()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def location_tree(db):
    """Minimal 4-level tree: KZ > Region > Almaty > [hidden+real venue] + RU subtree."""
    kz = Location.add_root(name="KZ", name_ru="KZ", name_kk="KZ", name_en="KZ", sort_order=1)
    region = kz.add_child(name="KZ Region", name_ru="KZ Region", name_kk="KZ Region", name_en="KZ Region", sort_order=1)
    city = region.add_child(name="Almaty", name_ru="Almaty", name_kk="Almaty", name_en="Almaty", sort_order=1)
    hidden = city.add_child(
        name="Other Venue",
        name_ru="Other Venue",
        name_kk="Other Venue",
        name_en="Other Venue",
        sort_order=9999,
        is_hidden=True,
    )
    real = city.add_child(name="Velodrome", name_ru="Velodrome", name_kk="Velodrome", name_en="Velodrome", sort_order=1)
    ru = Location.add_root(name="RU", name_ru="RU", name_kk="RU", name_en="RU", sort_order=2)
    ru_region = ru.add_child(
        name="RU Region", name_ru="RU Region", name_kk="RU Region", name_en="RU Region", sort_order=1
    )
    ru_city = ru_region.add_child(name="Moscow", name_ru="Moscow", name_kk="Moscow", name_en="Moscow", sort_order=1)
    ru_hidden = ru_city.add_child(
        name="Other Venue",
        name_ru="Other Venue",
        name_kk="Other Venue",
        name_en="Other Venue",
        sort_order=9999,
        is_hidden=True,
    )
    return {
        "kz": Location.objects.get(pk=kz.pk),
        "region": Location.objects.get(pk=region.pk),
        "city": Location.objects.get(pk=city.pk),
        "hidden": Location.objects.get(pk=hidden.pk),
        "real": Location.objects.get(pk=real.pk),
        "ru": Location.objects.get(pk=ru.pk),
        "ru_hidden": Location.objects.get(pk=ru_hidden.pk),
        "ru_city": Location.objects.get(pk=ru_city.pk),
        "ru_region": Location.objects.get(pk=ru_region.pk),
    }


def _make_comp(location, title="Race"):
    return Competition.objects.create(
        title_ru=title,
        date_start=_DATE,
        status=Competition.Status.APPROVED,
        location=location,
    )


# ---------------------------------------------------------------------------
# Competition.location_label
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_location_label_hidden_venue_shows_parent_city(location_tree):
    comp = Competition(location=location_tree["hidden"])
    assert comp.location_label == "Almaty"


@pytest.mark.django_db
def test_location_label_real_venue_shows_venue_name(location_tree):
    comp = Competition(location=location_tree["real"])
    assert comp.location_label == "Velodrome"


@pytest.mark.django_db
def test_location_label_none_is_empty_string():
    comp = Competition()
    assert comp.location_label == ""


# ---------------------------------------------------------------------------
# CompetitionListView location filter (descendant-aware)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_filter_country_returns_all_city_competitions(location_tree):
    _make_comp(location_tree["hidden"], "KZ Race")
    _make_comp(location_tree["ru_hidden"], "RU Race")

    resp = Client().get(
        "/ru/calendar/list/",
        {"location": location_tree["kz"].pk, "date_from": _DATE_FROM, "date_to": _DATE_TO},
    )
    assert resp.status_code == 200
    titles = [c.title for c in resp.context["competitions"]]
    assert "KZ Race" in titles
    assert "RU Race" not in titles


@pytest.mark.django_db
def test_list_filter_region_excludes_other_regions(location_tree):
    _make_comp(location_tree["hidden"], "KZ Race")
    _make_comp(location_tree["ru_hidden"], "RU Race")

    resp = Client().get(
        "/ru/calendar/list/",
        {"location": location_tree["region"].pk, "date_from": _DATE_FROM, "date_to": _DATE_TO},
    )
    assert resp.status_code == 200
    titles = [c.title for c in resp.context["competitions"]]
    assert "KZ Race" in titles
    assert "RU Race" not in titles


@pytest.mark.django_db
def test_list_filter_city_excludes_sibling_cities(location_tree):
    city2 = Location.objects.get(pk=location_tree["region"].pk).add_child(
        name="City2", name_ru="City2", name_kk="City2", name_en="City2", sort_order=2
    )
    hidden2 = city2.add_child(
        name="Other Venue",
        name_ru="Other Venue",
        name_kk="Other Venue",
        name_en="Other Venue",
        sort_order=9999,
        is_hidden=True,
    )
    _make_comp(location_tree["hidden"], "Almaty Race")
    _make_comp(Location.objects.get(pk=hidden2.pk), "City2 Race")

    resp = Client().get(
        "/ru/calendar/list/",
        {"location": location_tree["city"].pk, "date_from": _DATE_FROM, "date_to": _DATE_TO},
    )
    assert resp.status_code == 200
    titles = [c.title for c in resp.context["competitions"]]
    assert "Almaty Race" in titles
    assert "City2 Race" not in titles
