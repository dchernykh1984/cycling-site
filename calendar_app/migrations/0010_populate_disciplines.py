"""Data migration: populate DisciplineCategory, Discipline, and EventType with default values."""

from django.db import migrations

# ---------------------------------------------------------------------------
# Source data
# ---------------------------------------------------------------------------

# fmt: off
_CATEGORIES = [
    # (order, name_ru, name_en, name_kk)
    (1,  "Шоссе",           "Road Cycling",         "Жол велоспорты"),
    (2,  "Маунтинбайк",     "Mountain Bike",        "Таулы велосипед"),
    (3,  "Гравел",          "Gravel",               "Гравел"),
    (4,  "Циклокросс",      "Cyclocross",           "Циклокросс"),
    (5,  "Трек",            "Track Cycling",        "Трек велоспорты"),
    (6,  "BMX",             "BMX",                  "BMX"),
    (7,  "Лыжные гонки",    "Cross-Country Skiing", "Лыжжарыс"),
    (8,  "Бег",             "Running",              "Жүгіру"),
    (9,  "Триатлон",        "Triathlon",            "Триатлон"),
    (10, "Зимний триатлон", "Winter Triathlon",     "Қысқы триатлон"),
    (11, "Дуатлон",         "Duathlon",             "Дуатлон"),
]

_DISCIPLINES = {
    # category_order -> [(order, name_ru, name_en, name_kk), ...]
    1: [  # Шоссе
        (1,  "Групповая шоссейная гонка",                "Road Race",                     "Топтық жол жарысы"),
        (2,  "Индивидуальная гонка с раздельного старта", "Individual Time Trial",         "Жеке уақыт сынақ жарысы"),
        (3,  "Командная гонка с раздельного старта",     "Team Time Trial",               "Командалық уақыт сынақ жарысы"),
        (4,  "Критериум",                                "Criterium",                     "Критериум"),
        (5,  "Бревет",                                   "Brevet",                        "Бревет"),
        (6,  "Гран-Фондо",                               "Gran Fondo",                    "Гран-Фондо"),
        (7,  "Многодневная гонка (этапная)",              "Stage Race",                    "Кезеңдік жарыс"),
        (8,  "Эстафета",                                 "Relay",                         "Эстафет"),
        (9,  "Другое",                                   "Other",                         "Басқа"),
    ],
    2: [  # Маунтинбайк
        (1,  "Кросс-кантри олимпийское (XCO)",           "Cross-Country Olympic (XCO)",   "Кросс-кантри олимпиялық (XCO)"),
        (2,  "Кросс-кантри марафон (XCM)",               "Cross-Country Marathon (XCM)",  "Кросс-кантри марафон (XCM)"),
        (3,  "Кросс-кантри элиминатор (XCE)",            "Cross-Country Eliminator (XCE)","Кросс-кантри элиминатор (XCE)"),
        (4,  "Кросс-кантри короткий трек (XCC)",         "Cross-Country Short Track (XCC)","Кросс-кантри қысқа трек (XCC)"),
        (5,  "Даунхилл (DHI)",                           "Downhill (DHI)",                "Даунхилл (DHI)"),
        (6,  "Эндуро (EDR)",                             "Enduro (EDR)",                  "Эндуро (EDR)"),
        (7,  "Четырёхкросс (4X)",                        "Four-Cross (4X)",               "Төрт кросс (4X)"),
        (8,  "Дуал-слалом",                              "Dual Slalom",                   "Дуал-слалом"),
        (9,  "Трайал маунтинбайк",                       "Mountain Bike Trials",          "Таулы велосипед трайалы"),
        (10, "Трейл (МТБ)",                              "Trail (MTB)",                   "Трейл (МТБ)"),
        (11, "Эстафета",                                 "Relay",                         "Эстафет"),
        (12, "Другое",                                   "Other",                         "Басқа"),
    ],
    3: [  # Гравел
        (1, "Гравийная гонка",                           "Gravel Race",                   "Гравийлық жарыс"),
        (2, "Эстафета",                                  "Relay",                         "Эстафет"),
        (3, "Другое",                                    "Other",                         "Басқа"),
    ],
    4: [  # Циклокросс
        (1, "Циклокросс",                                "Cyclocross",                    "Циклокросс"),
        (2, "Эстафета",                                  "Relay",                         "Эстафет"),
        (3, "Другое",                                    "Other",                         "Басқа"),
    ],
    5: [  # Трек
        (1,  "Трековый спринт",                          "Track Sprint",                  "Трек спринті"),
        (2,  "Командный спринт",                         "Team Sprint",                   "Командалық спринт"),
        (3,  "Кейрин",                                   "Keirin",                        "Кейрин"),
        (4,  "Омниум",                                   "Omnium",                        "Омниум"),
        (5,  "Мэдисон",                                  "Madison",                       "Мэдисон"),
        (6,  "Гит 1 км (муж.) / 500 м (жен.)",           "1 km Time Trial",               "1 км уақыт сынақ жарысы"),
        (7,  "Индивидуальная гонка преследования",       "Individual Pursuit",            "Жеке қуу жарысы"),
        (8,  "Командная гонка преследования",            "Team Pursuit",                  "Командалық қуу жарысы"),
        (9,  "Скрэтч",                                   "Scratch Race",                  "Скрэтч жарысы"),
        (10, "Гонка по очкам (трек)",                    "Points Race",                   "Очкомен жарыс"),
        (11, "Темп-гонка",                               "Tempo Race",                    "Темп жарысы"),
        (12, "Эстафета",                                 "Relay",                         "Эстафет"),
        (13, "Другое",                                   "Other",                         "Басқа"),
    ],
    6: [  # BMX
        (1, "BMX-рейсинг (олимпийский)",                 "BMX Racing",                    "BMX жарысы (олимпиялық)"),
        (2, "BMX Фристайл Стрит",                        "BMX Freestyle Street",          "BMX Фристайл Стрит"),
        (3, "BMX Фристайл Дёрт",                         "BMX Freestyle Dirt",            "BMX Фристайл Дёрт"),
        (4, "Эстафета",                                  "Relay",                         "Эстафет"),
        (5, "Другое",                                    "Other",                         "Басқа"),
    ],
    7: [  # Лыжные гонки
        (1, "Спринт",                                    "Cross-Country Sprint",          "Лыжжарыс спринті"),
        (2, "Командный спринт",                          "Cross-Country Team Sprint",     "Лыжжарыс командалық спринт"),
        (3, "Гонка с раздельного старта",                "Individual Start",              "Жеке старт"),
        (4, "Масстарт",                                  "Mass Start",                    "Масстарт"),
        (5, "Марафон",                                   "Cross-Country Marathon",        "Лыжжарыс марафоны"),
        (6, "Пасьют (гонка преследования)",              "Pursuit",                       "Қуу жарысы"),
        (7, "Эстафета",                                  "Relay",                         "Эстафет"),
        (8, "Другое",                                    "Other",                         "Басқа"),
    ],
    8: [  # Бег
        (1,  "Спринт (100 м - 400 м)",                   "Sprint (100m - 400m)",          "Спринт (100 м - 400 м)"),
        (2,  "Средние дистанции (800 м - 1500 м)",       "Middle Distance (800m - 1500m)","Орта қашықтық (800 м - 1500 м)"),
        (3,  "Длинные дистанции (5000 м - 10000 м)",     "Long Distance (5000m - 10000m)","Ұзын қашықтық (5000 м - 10000 м)"),
        (4,  "Полумарафон",                              "Half Marathon",                 "Жартылай марафон"),
        (5,  "Марафон",                                  "Marathon",                      "Марафон"),
        (6,  "Ультрамарафон",                            "Ultramarathon",                 "Ультрамарафон"),
        (7,  "Трейлраннинг",                             "Trail Running",                 "Трейл жүгіру"),
        (8,  "Горный бег",                               "Mountain Running",              "Тау жүгіру"),
        (9,  "Бег по пересечённой местности",            "Cross-Country Running",         "Кросс жүгіру"),
        (10, "Эстафета",                                 "Relay",                         "Эстафет"),
        (11, "Другое",                                   "Other",                         "Басқа"),
    ],
    9: [  # Триатлон
        (1, "Супер-спринт триатлон",                     "Super Sprint Triathlon",        "Супер-спринт триатлон"),
        (2, "Спринт-триатлон",                           "Sprint Triathlon",              "Спринт-триатлон"),
        (3, "Олимпийский триатлон",                      "Olympic Triathlon",             "Олимпиялық триатлон"),
        (4, "Половинная дистанция (70.3)",               "Half Distance Triathlon",       "Жарты қашықтық триатлон"),
        (5, "Полная дистанция (Ironman)",                "Full Distance Triathlon",       "Толық қашықтық триатлон"),
        (6, "Ультра-триатлон (Double / Triple Ironman)", "Ultra Triathlon",               "Ультра-триатлон"),
        (7, "Кросс-триатлон (XTERRA)",                   "Cross Triathlon",               "Кросс-триатлон"),
        (8, "Эстафета",                                  "Relay",                         "Эстафет"),
        (9, "Другое",                                    "Other",                         "Басқа"),
    ],
    10: [  # Зимний триатлон
        (1, "Зимний триатлон спринт",                    "Winter Triathlon Sprint",       "Қысқы триатлон спринт"),
        (2, "Зимний триатлон стандарт",                  "Winter Triathlon Standard",     "Қысқы триатлон стандарт"),
        (3, "Эстафета",                                  "Relay",                         "Эстафет"),
        (4, "Другое",                                    "Other",                         "Басқа"),
    ],
    11: [  # Дуатлон
        (1, "Дуатлон",                                   "Duathlon",                      "Дуатлон"),
        (2, "Акватлон",                                  "Aquathlon",                     "Акватлон"),
        (3, "Аквабайк",                                  "Aquabike",                      "Аквабайк"),
        (4, "Зимний дуатлон",                            "Winter Duathlon",               "Қысқы дуатлон"),
        (5, "СвимРан",                                   "SwimRun",                       "СвимРан"),
        (6, "Эстафета",                                  "Relay",                         "Эстафет"),
        (7, "Другое",                                    "Other",                         "Басқа"),
    ],
}

_EVENT_TYPES = [
    # (order, name_ru, name_en, name_kk)
    (1,  "Гонка",                      "Race",                    "Жарыс"),
    (2,  "Контрольная тренировка",     "Unofficial Time Trial",   "Бақылау жаттығуы"),
    (3,  "Тренировка / Прогулка",      "Training / Leisure Ride", "Жаттығу / Серуен"),
    (4,  "Детская гонка",              "Kids Race",               "Балалар жарысы"),
    (5,  "Фестиваль",                  "Festival",                "Фестиваль"),
]
# fmt: on


def populate_disciplines(apps, schema_editor):
    DisciplineCategory = apps.get_model("calendar_app", "DisciplineCategory")
    Discipline = apps.get_model("calendar_app", "Discipline")

    cat_by_order = {}
    for order, name_ru, name_en, name_kk in _CATEGORIES:
        cat, _ = DisciplineCategory.objects.get_or_create(
            name_ru=name_ru,
            defaults={"name": name_ru, "name_en": name_en, "name_kk": name_kk, "order": order},
        )
        cat_by_order[order] = cat

    for cat_order, disciplines in _DISCIPLINES.items():
        cat = cat_by_order[cat_order]
        for order, name_ru, name_en, name_kk in disciplines:
            Discipline.objects.get_or_create(
                name_ru=name_ru,
                category=cat,
                defaults={"name": name_ru, "name_en": name_en, "name_kk": name_kk, "order": order},
            )


def populate_event_types(apps, schema_editor):
    EventType = apps.get_model("calendar_app", "EventType")
    for order, name_ru, name_en, name_kk in _EVENT_TYPES:
        EventType.objects.get_or_create(
            name_ru=name_ru,
            defaults={"name": name_ru, "name_en": name_en, "name_kk": name_kk, "order": order},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0009_discipline_category"),
    ]

    operations = [
        migrations.RunPython(populate_disciplines, migrations.RunPython.noop),
        migrations.RunPython(populate_event_types, migrations.RunPython.noop),
    ]
