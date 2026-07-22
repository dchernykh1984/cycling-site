"""Seed the geography the begaem.com calendars need.

The events agent may only create a venue (depth 4) under an existing city, so a race in a city the
tree does not have lands without a location at all. This migration adds the countries, regions and
cities the two begaem.com running calendars currently reference: 26 new countries plus the Russian
regions and cities missing from the earlier seeds.

Only the hierarchy down to the city is seeded. Every city also gets its hidden "Other location"
catch-all venue together with the LocationFallback mapping, so the API's fallback endpoint reuses it
instead of creating a second one. Concrete start venues are deliberately left to the agent, which
creates them per race from the announcement.

Nodes are matched by their Russian name and reused, including ones that were soft-deleted earlier
(production carries a deleted "Uzbekistan" root): deletion keeps the row and its materialized path,
so creating a namesake instead of restoring it would break the path's unique index.

New nodes go in through ``add_location_child`` rather than treebeard's ``add_child`` / ``add_root``.
The sorted insert those two perform assumes a sibling's path order matches its sort order, which
production does not satisfy -- the restored "Uzbekistan" sits last by path while its sort_order is 0
-- and the resulting path shift collides with the unique index.
"""

from django.db import migrations

_OTHER_REGION = ("Другой регион", "Басқа аймақ", "Other region")
_OTHER_CITY = ("Другой город", "Басқа қала", "Other city")
_OTHER_VENUE = ("Другая локация", "Басқа орын", "Other location")

# (country, [(region, [city, ...]), ...]) -- names as (ru, kk, en) triples. Regions and cities keep
# the Russian spelling for kk where no established Kazakh form exists, as in the earlier seeds.
WORLD = [
    (
        ("Беларусь", "Беларусь", "Belarus"),
        [(("Минск", "Минск", "Minsk"), [("Минск", "Минск", "Minsk")])],
    ),
    (
        ("Грузия", "Грузия", "Georgia"),
        [(("Тбилиси", "Тбилиси", "Tbilisi"), [("Тбилиси", "Тбилиси", "Tbilisi")])],
    ),
    (
        ("Армения", "Армения", "Armenia"),
        [(("Тавуш", "Тавуш", "Tavush"), [("Дилижан", "Дилижан", "Dilijan")])],
    ),
    (
        ("Узбекистан", "Өзбекстан", "Uzbekistan"),
        [
            (
                ("Самаркандская область", "Самарқанд облысы", "Samarkand Region"),
                [("Самарканд", "Самарқанд", "Samarkand")],
            )
        ],
    ),
    (
        ("Турция", "Түркия", "Turkey"),
        [
            (("Стамбул", "Стамбул", "Istanbul"), [("Стамбул", "Стамбул", "Istanbul")]),
            (("Анкара", "Анкара", "Ankara"), [("Шерефликочхисар", "Шерефликочхисар", "Sereflikochisar")]),
            (("Ризе", "Ризе", "Rize"), [("Айдер", "Айдер", "Ayder")]),
            (("Бурса", "Бурса", "Bursa"), [("Бурса", "Бурса", "Bursa")]),
        ],
    ),
    (
        ("Литва", "Литва", "Lithuania"),
        [(("Вильнюсский уезд", "Вильнюсский уезд", "Vilnius County"), [("Вильнюс", "Вильнюс", "Vilnius")])],
    ),
    (
        ("Польша", "Польша", "Poland"),
        [
            (
                ("Мазовецкое воеводство", "Мазовецкое воеводство", "Masovian Voivodeship"),
                [("Варшава", "Варшава", "Warsaw")],
            )
        ],
    ),
    (
        ("Чехия", "Чехия", "Czech Republic"),
        [
            (("Прага", "Прага", "Prague"), [("Прага", "Прага", "Prague")]),
            (
                ("Устецкий край", "Устецкий край", "Usti nad Labem Region"),
                [("Усти-над-Лабем", "Усти-над-Лабем", "Usti nad Labem")],
            ),
            (("Либерецкий край", "Либерецкий край", "Liberec Region"), [("Либерец", "Либерец", "Liberec")]),
        ],
    ),
    (
        ("Словакия", "Словакия", "Slovakia"),
        [(("Кошицкий край", "Кошицкий край", "Kosice Region"), [("Кошице", "Кошице", "Kosice")])],
    ),
    (
        ("Венгрия", "Венгрия", "Hungary"),
        [(("Будапешт", "Будапешт", "Budapest"), [("Будапешт", "Будапешт", "Budapest")])],
    ),
    (
        ("Германия", "Германия", "Germany"),
        [
            (("Берлин", "Берлин", "Berlin"), [("Берлин", "Берлин", "Berlin")]),
            (
                ("Северный Рейн-Вестфалия", "Северный Рейн-Вестфалия", "North Rhine-Westphalia"),
                [("Кёльн", "Кёльн", "Cologne")],
            ),
            (("Бавария", "Бавария", "Bavaria"), [("Мюнхен", "Мюнхен", "Munich")]),
        ],
    ),
    (
        ("Нидерланды", "Нидерланды", "Netherlands"),
        [
            (
                ("Северная Голландия", "Северная Голландия", "North Holland"),
                [("Амстердам", "Амстердам", "Amsterdam")],
            )
        ],
    ),
    (
        ("Дания", "Дания", "Denmark"),
        [
            (
                ("Столичная область", "Столичная область", "Capital Region"),
                [("Копенгаген", "Копенгаген", "Copenhagen")],
            )
        ],
    ),
    (
        ("Финляндия", "Финляндия", "Finland"),
        [(("Уусимаа", "Уусимаа", "Uusimaa"), [("Хельсинки", "Хельсинки", "Helsinki")])],
    ),
    (
        ("Исландия", "Исландия", "Iceland"),
        [
            (
                ("Столичный регион", "Столичный регион", "Capital Region"),
                [("Рейкьявик", "Рейкьявик", "Reykjavik")],
            )
        ],
    ),
    (
        ("Великобритания", "Ұлыбритания", "United Kingdom"),
        [(("Уэльс", "Уэльс", "Wales"), [("Кардифф", "Кардифф", "Cardiff")])],
    ),
    (
        ("Швейцария", "Швейцария", "Switzerland"),
        [(("Во", "Во", "Vaud"), [("Лозанна", "Лозанна", "Lausanne")])],
    ),
    (
        ("Италия", "Италия", "Italy"),
        [(("Тоскана", "Тоскана", "Tuscany"), [("Флоренция", "Флоренция", "Florence")])],
    ),
    (
        ("Испания", "Испания", "Spain"),
        [
            (
                ("Валенсия", "Валенсия", "Valencian Community"),
                [("Валенсия", "Валенсия", "Valencia")],
            ),
            (("Каталония", "Каталония", "Catalonia"), [("Барселона", "Барселона", "Barcelona")]),
        ],
    ),
    (
        ("Северная Македония", "Солтүстік Македония", "North Macedonia"),
        [(("Скопье", "Скопье", "Skopje"), [("Скопье", "Скопье", "Skopje")])],
    ),
    (
        ("Кипр", "Кипр", "Cyprus"),
        [(("Ларнака", "Ларнака", "Larnaca"), [("Ларнака", "Ларнака", "Larnaca")])],
    ),
    (
        ("Египет", "Мысыр", "Egypt"),
        [
            (
                ("Южный Синай", "Южный Синай", "South Sinai"),
                [("Шарм-эш-Шейх", "Шарм-эш-Шейх", "Sharm El Sheikh")],
            ),
            (("Луксор", "Луксор", "Luxor"), [("Луксор", "Луксор", "Luxor")]),
        ],
    ),
    (
        ("ЮАР", "Оңтүстік Африка Республикасы", "South Africa"),
        [
            (
                ("Западно-Капская провинция", "Западно-Капская провинция", "Western Cape"),
                [("Кейптаун", "Кейптаун", "Cape Town")],
            )
        ],
    ),
    (
        ("США", "АҚШ", "United States"),
        [
            (("Иллинойс", "Иллинойс", "Illinois"), [("Чикаго", "Чикаго", "Chicago")]),
            (("Нью-Йорк", "Нью-Йорк", "New York"), [("Нью-Йорк", "Нью-Йорк", "New York")]),
        ],
    ),
    (
        ("Бразилия", "Бразилия", "Brazil"),
        [(("Сан-Паулу", "Сан-Паулу", "Sao Paulo"), [("Сан-Паулу", "Сан-Паулу", "Sao Paulo")])],
    ),
    (
        ("Австралия", "Аустралия", "Australia"),
        [
            (
                ("Новый Южный Уэльс", "Новый Южный Уэльс", "New South Wales"),
                [("Сидней", "Сидней", "Sydney")],
            )
        ],
    ),
]

# Russian regions and cities the calendar references. Regions already in the tree are reused (they
# are looked up by their Russian name), so the outcome is the same on a seeded and on a fresh
# database -- only the missing nodes are created.
RUSSIA = [
    (
        ("Нижегородская область", "Нижегородская область", "Nizhny Novgorod Oblast"),
        [("Нижний Новгород", "Нижний Новгород", "Nizhny Novgorod")],
    ),
    (
        ("Чувашская Республика", "Чуваш Республикасы", "Chuvash Republic"),
        [("Чебоксары", "Чебоксары", "Cheboksary")],
    ),
    (
        ("Амурская область", "Амурская область", "Amur Oblast"),
        [("Благовещенск", "Благовещенск", "Blagoveshchensk")],
    ),
    (
        ("Ставропольский край", "Ставропольский край", "Stavropol Krai"),
        [
            ("Пятигорск", "Пятигорск", "Pyatigorsk"),
            ("Железноводск", "Железноводск", "Zheleznovodsk"),
        ],
    ),
    (
        ("Приморский край", "Приморский край", "Primorsky Krai"),
        [("Владивосток", "Владивосток", "Vladivostok")],
    ),
    (
        ("Республика Саха (Якутия)", "Саха Республикасы (Якутия)", "Sakha Republic (Yakutia)"),
        [("Якутск", "Якутск", "Yakutsk")],
    ),
    (
        ("Республика Башкортостан", "Башқұртстан Республикасы", "Republic of Bashkortostan"),
        [("Уфа", "Уфа", "Ufa"), ("Абзаково", "Абзаково", "Abzakovo")],
    ),
    (
        ("Кабардино-Балкарская Республика", "Кабарды-Балқар Республикасы", "Kabardino-Balkar Republic"),
        [("Нальчик", "Нальчик", "Nalchik"), ("Терскол", "Терскол", "Terskol")],
    ),
    (
        ("Забайкальский край", "Забайкальский край", "Zabaykalsky Krai"),
        [("Чита", "Чита", "Chita"), ("Новая Чара", "Новая Чара", "Novaya Chara")],
    ),
    (
        ("Камчатский край", "Камчатский край", "Kamchatka Krai"),
        [("Петропавловск-Камчатский", "Петропавловск-Камчатский", "Petropavlovsk-Kamchatsky")],
    ),
    (
        ("Самарская область", "Самарская область", "Samara Oblast"),
        [("Самара", "Самара", "Samara")],
    ),
    (
        ("Республика Татарстан", "Татарстан Республикасы", "Republic of Tatarstan"),
        [("Альметьевск", "Альметьевск", "Almetyevsk"), ("Нижнекамск", "Нижнекамск", "Nizhnekamsk")],
    ),
    (
        ("Красноярский край", "Красноярский край", "Krasnoyarsk Krai"),
        [("Талнах", "Талнах", "Talnakh")],
    ),
    (("Тверская область", "Тверская область", "Tver Oblast"), [("Завидово", "Завидово", "Zavidovo")]),
    (
        ("Московская область", "Мәскеу облысы", "Moscow Oblast"),
        [("Фрязино", "Фрязино", "Fryazino"), ("Хотьково", "Хотьково", "Khotkovo")],
    ),
    (
        ("Краснодарский край", "Краснодарский край", "Krasnodar Krai"),
        [("Красная Поляна", "Красная Поляна", "Krasnaya Polyana"), ("Сириус", "Сириус", "Sirius")],
    ),
    (
        ("Ленинградская область", "Ленинградская область", "Leningrad Oblast"),
        [("Кобона", "Кобона", "Kobona")],
    ),
    (
        ("Санкт-Петербург", "Санкт-Петербург", "Saint Petersburg"),
        [("Пушкин", "Пушкин", "Pushkin"), ("Павловск", "Павловск", "Pavlovsk")],
    ),
]


def _restored(node):
    """Reuse a node that was soft-deleted earlier: deletion keeps the row (and its materialized
    path), so adding a second node with the same name would collide on the path's unique index."""
    if node is not None and node.is_deleted:
        node.is_deleted = False
        node.save(update_fields=["is_deleted"])
    return node


def _siblings(parent):
    """The parent's children by path range rather than ``get_children()``.

    treebeard short-circuits ``get_children()`` to an empty queryset whenever ``numchild`` is 0, so
    a counter that has drifted would make an existing child invisible here and this seed would add a
    second one. ``add_location_child`` avoids the same trap the same way.
    """
    from locations.models import Location

    return Location.objects.filter(
        depth=parent.depth + 1, path__range=Location._get_children_path_interval(parent.path)
    )


def _child(parent, names, sort_order, *, hidden=False):
    """Return the parent's child with this Russian name, creating it when absent."""
    from locations.models import add_location_child

    ru, kk, en = names
    # A live namesake wins over a soft-deleted one: rejecting a proposed city leaves the row behind,
    # so "proposed, rejected, added again" is a normal state and resurrecting the dead one would
    # leave two live cities with the same name.
    existing = _restored(_siblings(parent).filter(name_ru=ru).order_by("is_deleted", "path").first())
    if existing is not None:
        return existing
    return add_location_child(
        parent, name=ru, name_ru=ru, name_kk=kk, name_en=en, sort_order=sort_order, is_hidden=hidden
    )


def _add_city(region, names, sort_order, *, hidden=False):
    """Add the city plus its hidden catch-all venue and the fallback mapping that names it."""
    from locations.models import LocationFallback

    city = _child(region, names, sort_order, hidden=hidden)
    if not LocationFallback.objects.filter(city=city).exists():
        venue = _child(city, _OTHER_VENUE, 9999, hidden=True)
        LocationFallback.objects.get_or_create(city=city, defaults={"location": venue})
    return city


def _add_region(country, names, sort_order, cities, *, hidden=False):
    """Add (or reuse) the region and append the cities after whatever it already holds."""
    region = _child(country, names, sort_order, hidden=hidden)
    start = _siblings(region).filter(is_deleted=False).exclude(sort_order=9999).count() + 1
    for order, city_names in enumerate(cities, start=start):
        _add_city(region, city_names, order)
    # The catch-alls are placeholders for a human to pick, not places: production keeps every one of
    # them hidden so they stay out of the pickers, and the ones seeded here must match.
    _add_city(region, _OTHER_CITY, 9999, hidden=True)


def _add_country(names, regions, sort_order):
    from locations.models import Location, add_location_child

    ru, kk, en = names
    country = _restored(Location.objects.filter(depth=1, name_ru=ru).order_by("is_deleted", "path").first())
    if country is None:
        country = add_location_child(None, name=ru, name_ru=ru, name_kk=kk, name_en=en, sort_order=sort_order)
    for region_order, (region_names, cities) in enumerate(regions, start=1):
        _add_region(country, region_names, region_order, cities)
    # Mirror the structure Russia already has, so a reviewer can still place an event in the
    # country when its region is not one of the seeded ones.
    _add_region(country, _OTHER_REGION, 9999, [], hidden=True)


def add_locations(apps, schema_editor):
    from locations.models import Location

    for country_order, (country_names, regions) in enumerate(WORLD, start=10):
        _add_country(country_names, regions, country_order)

    # Every other lookup here tolerates a missing node; this one must too. An admin may rename the
    # root, and a database where the earlier seed never ran has none at all -- neither is a reason
    # to fail the deploy, since the countries above were already added.
    russia = Location.objects.filter(depth=1, name_ru="Россия", is_deleted=False).order_by("path").first()
    if russia is None:
        return
    for region_order, (region_names, cities) in enumerate(RUSSIA, start=100):
        _add_region(russia, region_names, region_order, cities)


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0012_location_fallback_for"),
    ]

    operations = [
        migrations.RunPython(add_locations, migrations.RunPython.noop),
    ]
