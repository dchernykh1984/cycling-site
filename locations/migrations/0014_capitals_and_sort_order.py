"""Add the seeded countries' capitals and give the whole tree a deliberate order.

The site renders locations in *path* order -- that is, creation order -- because add_location_child
appends instead of using treebeard's sorted insert. ``sort_order`` was stored but never consulted,
so the lists read in the order things happened to be added. This migration backfills sort_order from
the current path order (nothing moves by accident), then sets the order the site wants:

* countries: Kazakhstan, Kyrgyzstan, Russia, China, then the rest, catch-alls last;
* Kazakhstan: Almaty, Astana, Almaty Region, Akmola Region (the one around Astana), then the rest;
* Russia: Moscow, Saint Petersburg, Moscow Oblast, Leningrad Oblast, then the rest;
* every other country: its capital's region first, and the capital first inside that region.

The capital of each country seeded in 0013 is added here when it was missing -- several of those
countries only carried the town a race happened to be in.
"""

from django.db import migrations

_CATCH_ALL = {"Другая страна", "Другой регион", "Другой город", "Другая локация"}
_OTHER_VENUE = ("Другая локация", "Басқа орын", "Other location")

# The four closest countries lead the list; everything else keeps its existing relative order.
ROOT_LEADERS = ["Казахстан", "Кыргызстан", "Россия", "Китай"]
KZ_LEADERS = ["Алматы", "Астана", "Алматинская область", "Акмолинская область"]
RU_LEADERS = ["Москва", "Санкт-Петербург", "Московская область", "Ленинградская область"]

# country -> (region, city) of its capital, as (ru, kk, en) triples. Entries that already exist are
# reused by name; the rest are created here, so every seeded country has its capital.
CAPITALS = {
    # Kazakhstan and Russia have their own leader lists above; the other two close countries are
    # ordered by capital like everyone else, and both already carry theirs as a depth-2 node.
    "Кыргызстан": (("Бишкек", "Бішкек", "Bishkek"), ("Бишкек", "Бішкек", "Bishkek")),
    "Китай": (("Пекин", "Пекин", "Beijing"), ("Пекин", "Пекин", "Beijing")),
    "Беларусь": (("Минск", "Минск", "Minsk"), ("Минск", "Минск", "Minsk")),
    "Грузия": (("Тбилиси", "Тбилиси", "Tbilisi"), ("Тбилиси", "Тбилиси", "Tbilisi")),
    "Армения": (("Ереван", "Ереван", "Yerevan"), ("Ереван", "Ереван", "Yerevan")),
    "Узбекистан": (("Ташкент", "Ташкент", "Tashkent"), ("Ташкент", "Ташкент", "Tashkent")),
    "Турция": (("Анкара", "Анкара", "Ankara"), ("Анкара", "Анкара", "Ankara")),
    "Литва": (("Вильнюсский уезд", "Вильнюсский уезд", "Vilnius County"), ("Вильнюс", "Вильнюс", "Vilnius")),
    "Польша": (
        ("Мазовецкое воеводство", "Мазовецкое воеводство", "Masovian Voivodeship"),
        ("Варшава", "Варшава", "Warsaw"),
    ),
    "Чехия": (("Прага", "Прага", "Prague"), ("Прага", "Прага", "Prague")),
    "Словакия": (
        ("Братиславский край", "Братиславский край", "Bratislava Region"),
        ("Братислава", "Братислава", "Bratislava"),
    ),
    "Венгрия": (("Будапешт", "Будапешт", "Budapest"), ("Будапешт", "Будапешт", "Budapest")),
    "Германия": (("Берлин", "Берлин", "Berlin"), ("Берлин", "Берлин", "Berlin")),
    "Нидерланды": (
        ("Северная Голландия", "Северная Голландия", "North Holland"),
        ("Амстердам", "Амстердам", "Amsterdam"),
    ),
    "Дания": (("Столичная область", "Столичная область", "Capital Region"), ("Копенгаген", "Копенгаген", "Copenhagen")),
    "Финляндия": (("Уусимаа", "Уусимаа", "Uusimaa"), ("Хельсинки", "Хельсинки", "Helsinki")),
    "Исландия": (("Столичный регион", "Столичный регион", "Capital Region"), ("Рейкьявик", "Рейкьявик", "Reykjavik")),
    "Великобритания": (("Англия", "Англия", "England"), ("Лондон", "Лондон", "London")),
    "Швейцария": (("Берн", "Берн", "Bern"), ("Берн", "Берн", "Bern")),
    "Италия": (("Лацио", "Лацио", "Lazio"), ("Рим", "Рим", "Rome")),
    "Испания": (("Мадрид", "Мадрид", "Community of Madrid"), ("Мадрид", "Мадрид", "Madrid")),
    "Северная Македония": (("Скопье", "Скопье", "Skopje"), ("Скопье", "Скопье", "Skopje")),
    "Кипр": (("Никосия", "Никосия", "Nicosia"), ("Никосия", "Никосия", "Nicosia")),
    "Египет": (("Каир", "Каир", "Cairo"), ("Каир", "Каир", "Cairo")),
    # South Africa has three capitals; Pretoria is the seat of government.
    "ЮАР": (("Гаутенг", "Гаутенг", "Gauteng"), ("Претория", "Претория", "Pretoria")),
    "США": (
        ("Округ Колумбия", "Округ Колумбия", "District of Columbia"),
        ("Вашингтон", "Вашингтон", "Washington"),
    ),
    "Бразилия": (
        ("Федеральный округ", "Федеральный округ", "Federal District"),
        ("Бразилиа", "Бразилиа", "Brasilia"),
    ),
    "Австралия": (
        ("Австралийская столичная территория", "Австралийская столичная территория", "Australian Capital Territory"),
        ("Канберра", "Канберра", "Canberra"),
    ),
}


def _siblings(parent):
    """The parent's children by path range: ``get_children()`` returns nothing on a drifted
    ``numchild``, which would make an existing child invisible and add a second one."""
    from locations.models import Location

    return Location.objects.filter(
        depth=parent.depth + 1, path__range=Location._get_children_path_interval(parent.path)
    )


def _child(parent, names, *, hidden=False):
    """The parent's child with this Russian name, created (appended) when absent.

    A live namesake wins over a soft-deleted one, so a place that was proposed, rejected and later
    added again is reused rather than resurrected alongside its living twin.
    """
    from locations.models import add_location_child

    ru, kk, en = names
    existing = _siblings(parent).filter(name_ru=ru).order_by("is_deleted", "path").first()
    if existing is not None:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.save(update_fields=["is_deleted"])
        return existing
    return add_location_child(parent, name=ru, name_ru=ru, name_kk=kk, name_en=en, sort_order=0, is_hidden=hidden)


def _ensure_capitals():
    from locations.models import Location, LocationFallback

    for country_ru, (region_names, city_names) in CAPITALS.items():
        country = Location.objects.filter(depth=1, name_ru=country_ru, is_deleted=False).first()
        if country is None:  # the country seed did not run (a database predating 0013)
            continue
        city = _child(_child(country, region_names), city_names)
        if not LocationFallback.objects.filter(city=city).exists():
            venue = _child(city, _OTHER_VENUE, hidden=True)
            LocationFallback.objects.get_or_create(city=city, defaults={"location": venue})


def _renumber(children, leaders=()):
    """Number the children: ``leaders`` first in that order, catch-alls last, the rest as they are.

    ``children`` must arrive in path order, which is what the site showed until now, so anything not
    named explicitly keeps the position it had.
    """
    lead = {name: index + 1 for index, name in enumerate(leaders)}
    updated, following = [], 100
    for node in children:
        if node.name_ru in _CATCH_ALL:
            node.sort_order = 9999
        elif node.name_ru in lead:
            node.sort_order = lead[node.name_ru]
        else:
            following += 1
            node.sort_order = following
        updated.append(node)
    return updated


def _leaders_for(node) -> list:
    """Which children of ``node`` should lead its list."""
    if node.depth == 1:
        if node.name_ru == "Казахстан":
            return KZ_LEADERS
        if node.name_ru == "Россия":
            return RU_LEADERS
        capital = CAPITALS.get(node.name_ru)
        return [capital[0][0]] if capital else []
    if node.depth == 2:
        # Derive the parent from the path: treebeard's get_parent() raises on an orphaned node
        # (a hard-deleted country left behind by manual cleanup) rather than returning None.
        from locations.models import Location

        parent = Location.objects.filter(path=node.path[: -Location.steplen], depth=1).first()
        capital = CAPITALS.get(parent.name_ru) if parent is not None else None
        if capital and node.name_ru == capital[0][0]:
            return [capital[1][0]]
    return []


def apply_order(apps, schema_editor):
    from locations.models import Location

    _ensure_capitals()

    roots = list(Location.objects.filter(depth=1, is_deleted=False).order_by("path"))
    updated = _renumber(roots, ROOT_LEADERS)
    for node in Location.objects.filter(depth__in=[1, 2, 3], is_deleted=False).order_by("path"):
        children = list(node.get_children().filter(is_deleted=False).order_by("path"))
        updated.extend(_renumber(children, _leaders_for(node)))
    Location.objects.bulk_update(updated, ["sort_order"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0013_add_world_and_russia_locations"),
    ]

    operations = [
        migrations.RunPython(apply_order, migrations.RunPython.noop),
    ]
