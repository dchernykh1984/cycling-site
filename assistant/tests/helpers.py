"""People, places and events the assistant's tests share."""

import datetime
import uuid

from accounts.models import User
from calendar_app.models import Competition
from locations.models import Location


def user(name: str = "admin", role: str = User.Role.ADMIN) -> User:
    person = User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)
    person.api_token = uuid.uuid4()
    person.save(update_fields=["api_token"])
    return person


def city(name_ru: str = "Almaty", name_en: str = "Almaty", lat: float | None = 43.24, lng: float | None = 76.89):
    """A country, its region and a city in it, with the city's hidden catch-all venue."""
    country = Location.add_root(name_ru="Kazakhstan", name_kk="Qazaqstan", name_en="Kazakhstan")
    region = country.add_child(name_ru="Almaty Region", name_en="Almaty Region")
    town = region.add_child(name_ru=name_ru, name_en=name_en, lat=lat, lng=lng)
    town.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
    return town


def venue(town=None, name: str = "Giant shop, Abay 47", lat: float = 43.2389, lng: float = 76.9453):
    return (town or city()).add_child(name_ru=name, name_en=name, lat=lat, lng=lng)


def competition(**kwargs) -> Competition:
    fields = {
        "title_ru": "Race",
        "date_start": datetime.date(2026, 11, 20),
        "status": Competition.Status.APPROVED,
        **kwargs,
    }
    if "location" not in fields:
        fields["location"] = venue()
    return Competition.objects.create(**fields)
