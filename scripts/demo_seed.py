"""Demo content for a local database, to look at a skin in (skins/README.md).

Run inside a freshly migrated database with ``manage.py shell``; the migrations already bring the
event types, disciplines, the location tree and the Wagtail pages. Dates are counted from today in
the site's time zone, so the month grid, the 30-day list and the map always have something on them.
Every seeded account signs in with the password in PASSWORD.
"""

import datetime
import uuid

from allauth.account.models import EmailAddress
from django.apps import apps
from django.db import models
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition, CompetitionMaterial, Discipline, EventType
from knowledge.models import KnowledgeArticle
from locations.models import Level, Location
from news.models import NewsArticle
from protocols.models import Protocol
from registrations.models import CompetitionRegistration, RegistrationCategory

TODAY = timezone.localdate()
NOON = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(12, 0)))
PASSWORD = "visual-pass-1"  # noqa: S105 -- demo accounts in a local database only


def day(offset):
    return TODAY + datetime.timedelta(days=offset)


def user(name, role, theme="light"):
    member = User.objects.create_user(
        username=name,
        email=f"{name}@example.com",
        password=PASSWORD,
        role=role,
        first_name=name.split("_")[0].title(),
        last_name="Visual",
        theme=theme,
    )
    EmailAddress.objects.create(user=member, email=member.email, verified=True, primary=True)
    return member


organizer = user("organizer", User.Role.ORGANIZER)
visitors = {f"{who}_{theme}": (who, theme) for who in ("member", "admin") for theme in ("light", "dark")}
for name, (who, theme) in visitors.items():
    user(name, User.Role.ADMIN if who == "admin" else User.Role.PARTICIPANT, theme)

city = Location.objects.filter(depth=Level.CITY, is_hidden=False).order_by("pk").first()
# A made-up point: the map only needs a marker somewhere, not a real venue.
venue = Location.propose_venue(city, "Visual Square", lat=43, lng=77, approved=True)
types = list(EventType.objects.order_by("pk")[:2])
disciplines = list(Discipline.objects.order_by("pk")[:2])


def event(title, offset, *, kind=0, end=None, **extra):
    comp = Competition.objects.create(
        title_ru=title,
        title_en=title,
        description_ru=f"<p>{title}: start and finish at the main square, three distances.</p>",
        date_start=day(offset),
        date_end=day(end) if end is not None else None,
        location=venue,
        submitted_by=organizer,
        status=extra.pop("status", Competition.Status.APPROVED),
        **extra,
    )
    comp.event_types.set([types[kind]])
    comp.disciplines.set(disciplines)
    return comp


upcoming = event(
    "Gran Fondo Alatau",
    2,
    url_registration="https://example.com/register",
    url_regulations="https://example.com/regulations",
    registration_enabled=True,
    registration_mode=Competition.RegistrationMode.FREE,
)
for first, last in (("Aigerim", "Sadykova"), ("Ivan", "Petrov"), ("Timur", "Bekov")):
    CompetitionRegistration.objects.create(
        competition=upcoming, first_name=first, last_name=last, birth_date=datetime.date(1990, 5, 1), gender="M"
    )
# Categories long enough that a phone scrolls through each, so the sticky category band has a
# page to stick on.
for order, name in enumerate(("Elite", "Masters", "Juniors"), start=1):
    category = RegistrationCategory.objects.create(competition=upcoming, name=name, order=order)
    for n in range(8):
        CompetitionRegistration.objects.create(
            competition=upcoming,
            category=category,
            first_name=f"Rider{n}",
            last_name=f"{name}{n}",
            birth_date=datetime.date(1980 + n, 1, 1),
            gender="M",
        )
finished = event("Tien Shan Trail", -3, kind=1, url_results="https://example.com/results")
Protocol.objects.create(competition=finished, protocol_type="absolute", is_live=False)
Protocol.objects.create(competition=finished, protocol_type="group", is_live=True, stage_label="Stage 2")
CompetitionMaterial.objects.create(competition=finished, title="Photos", url="https://example.com/photos")
event("Night Ride", 10, kind=1)
event("Kids Cup", 20, end=21)
event("Pending Race", 15, status=Competition.Status.PENDING_APPROVAL)
Location.propose_venue(city, "Pending Venue", lat=venue.lat, lng=venue.lng, submitted_by=organizer)

news = [
    NewsArticle.objects.create(
        title=f"Season news {n}",
        intro="Registration is open for the autumn races.",
        body="<p>The autumn season starts with a gran fondo and a trail race.</p>",
        published_at=NOON - datetime.timedelta(days=n),
        published_by=organizer,
    )
    for n in (1, 2)
]
guide = KnowledgeArticle.objects.create(
    title="How to pick a first race",
    locale="ru",
    body="<p>Start short, check the cut-off times and the climbing.</p>",
    category="Basics",
    published_at=NOON,
    published_by=organizer,
)

# A random token or a creation time rendered on a page would differ between the two sides.
for comp in Competition.objects.all():
    Competition.objects.filter(pk=comp.pk).update(upload_token=uuid.UUID(int=comp.pk), approved_at=NOON)

for model in apps.get_models():
    stamps = {
        field.name: NOON
        for field in model._meta.concrete_fields
        if isinstance(field, models.DateTimeField)
        and (
            getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False) or field.default is timezone.now
        )
    }
    if stamps:
        model._default_manager.all().update(**stamps)
User.objects.update(last_login=NOON, date_joined=NOON)
