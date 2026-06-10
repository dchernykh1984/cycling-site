"""
Add the four Xinjiang border prefectures that directly adjoin Kazakhstan,
the closest of which (Ili Kazakh Autonomous Prefecture) borders Almaty
region via the Khorgos crossing.

Also expands the existing Xinjiang region with three more southern cities.
"""

from django.db import migrations

_OTHER = {
    "city": {"ru": "Другой город", "kk": "Басқа қала", "en": "Other city"},
    "venue": {"ru": "Другая локация", "kk": "Басқа орын", "en": "Other location"},
}

# ---------------------------------------------------------------------------
# 3 extra cities for the existing Синьцзян region
# (Урумчи, Инин, Кашгар, Хами, Корла already present from migration 0004)
# ---------------------------------------------------------------------------

XINJIANG_EXTRA_CITIES = [
    {"ru": "Аксу", "kk": "Ақсу", "en": "Aksu", "so": 6},
    {"ru": "Хотан", "kk": "Хотан", "en": "Hotan", "so": 7},
    {"ru": "Атуши", "kk": "Атуші", "en": "Artux", "so": 8},
]

# ---------------------------------------------------------------------------
# Four Xinjiang prefectures that border Kazakhstan
# (none of these cities duplicate the ones already in Синьцзян)
# ---------------------------------------------------------------------------

XINJIANG_BORDER_PREFECTURES = [
    # Most adjacent to Almaty via the Khorgos / Horgos border crossing
    {
        "ru": "Или-Казахский автономный округ",
        "kk": "Іле-Қазақ автономиялық облысы",
        "en": "Ili Kazakh Autonomous Prefecture",
        "so": 12,
        "cities": [
            {"ru": "Хоргос", "kk": "Хоргос", "en": "Khorgos", "so": 1},
            {"ru": "Синюань", "kk": "Синюань", "en": "Xinyuan", "so": 2},
            {"ru": "Нилка", "kk": "Нілқа", "en": "Nilka", "so": 3},
            {"ru": "Чапчал", "kk": "Шапшал", "en": "Qapqal", "so": 4},
            {"ru": "Текес", "kk": "Текес", "en": "Tekes", "so": 5},
        ],
    },
    # Adjacent to Kazakhstan via Alashankou / Dostyk rail crossing
    {
        "ru": "Борталинский монгольский автономный округ",
        "kk": "Бортала Моңғол автономиялық облысы",
        "en": "Bortala Mongol Autonomous Prefecture",
        "so": 13,
        "cities": [
            {"ru": "Боле", "kk": "Боле", "en": "Bole", "so": 1},
            {"ru": "Алашанькоу", "kk": "Алашанькоу", "en": "Alashankou", "so": 2},
            {"ru": "Цзинхэ", "kk": "Цзинхэ", "en": "Jinghe", "so": 3},
        ],
    },
    # Borders Kazakhstan further north (Tarbagatay / Чочек corridor)
    {
        "ru": "Тачэнский округ",
        "kk": "Тарбағатай округі",
        "en": "Tacheng Prefecture",
        "so": 14,
        "cities": [
            {"ru": "Тачэн", "kk": "Шауешек", "en": "Tacheng", "so": 1},
            {"ru": "Эмин", "kk": "Йеміні", "en": "Yumin", "so": 2},
            {"ru": "Толи", "kk": "Торы", "en": "Toli", "so": 3},
            {"ru": "Шаван", "kk": "Шауан", "en": "Shawan", "so": 4},
        ],
    },
    # Borders East Kazakhstan and Altai region of Russia
    {
        "ru": "Алтайский округ Синьцзяна",
        "kk": "Алтай округі (Шыңжаң)",
        "en": "Altay Prefecture (Xinjiang)",
        "so": 15,
        "cities": [
            {"ru": "Алтай", "kk": "Алтай", "en": "Altay", "so": 1},
            {"ru": "Буэрцзинь", "kk": "Бұршін", "en": "Burqin", "so": 2},
            {"ru": "Цинхэ", "kk": "Цинхэ", "en": "Qinghe", "so": 3},
            {"ru": "Фуюнь", "kk": "Фуюнь", "en": "Fuyun", "so": 4},
            {"ru": "Хабахэ", "kk": "Хабахэ", "en": "Habahe", "so": 5},
        ],
    },
]


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def add_locations(apps, schema_editor):
    from locations.models import Location

    o_city = _OTHER["city"]
    o_venue = _OTHER["venue"]

    def add_venue(parent):
        parent.add_child(
            name=o_venue["ru"],
            name_ru=o_venue["ru"],
            name_kk=o_venue["kk"],
            name_en=o_venue["en"],
            sort_order=9999,
            is_hidden=True,
        )

    def add_other_city(parent):
        city_node = parent.add_child(
            name=o_city["ru"],
            name_ru=o_city["ru"],
            name_kk=o_city["kk"],
            name_en=o_city["en"],
            sort_order=9999,
        )
        add_venue(city_node)

    china = Location.objects.get(name_ru="Китай", depth=1)
    xinjiang = Location.objects.get(name_ru="Синьцзян", depth=2, path__startswith=china.path)

    # Expand existing Xinjiang with 3 more southern cities
    for city_data in XINJIANG_EXTRA_CITIES:
        city = xinjiang.add_child(
            name=city_data["ru"],
            name_ru=city_data["ru"],
            name_kk=city_data["kk"],
            name_en=city_data["en"],
            sort_order=city_data["so"],
        )
        add_venue(city)

    # Add four border prefecture regions under China
    for reg_data in XINJIANG_BORDER_PREFECTURES:
        region = china.add_child(
            name=reg_data["ru"],
            name_ru=reg_data["ru"],
            name_kk=reg_data["kk"],
            name_en=reg_data["en"],
            sort_order=reg_data["so"],
        )
        for city_data in reg_data["cities"]:
            city = region.add_child(
                name=city_data["ru"],
                name_ru=city_data["ru"],
                name_kk=city_data["kk"],
                name_en=city_data["en"],
                sort_order=city_data["so"],
            )
            add_venue(city)
        add_other_city(region)


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0006_add_russia_china_locations"),
    ]

    operations = [
        migrations.RunPython(add_locations, migrations.RunPython.noop),
    ]
