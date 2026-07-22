"""Seed every remaining country with its capital, so an event abroad always has somewhere to go.

Countries are admin-only: the events agent may propose a region or a city, never a root. Until now
the tree held only the 31 countries earlier seeds happened to need, so a race anywhere else was
filed under the catch-all country -- or, once the agent needed a country to hang a region on, not
placed at all. Seeding the whole set closes that.

Each country gets the first-level division its capital belongs to, the capital itself, and the same
catch-all placeholders every other branch has (a hidden "Другой регион", a hidden "Другой город" in
the capital's region, and the hidden "Другая локация" venue with its LocationFallback row). Regions
and cities beyond the capital are deliberately left out: the agent proposes those as it meets them
and an admin approves, which keeps the tree to places that are actually used.

Kazakh names repeat the Russian ones, as in the earlier seeds, except where an established Kazakh
form already exists in the tree. Nothing here is created twice: a country, region or city that is
already present is matched by its Russian name and reused.
"""

from django.db import migrations

_OTHER_REGION = ("Другой регион", "Басқа аймақ", "Other region")
_OTHER_CITY = ("Другой город", "Басқа қала", "Other city")
_OTHER_VENUE = ("Другая локация", "Басқа орын", "Other location")

# (country_ru, country_en, region_ru, region_en, capital_ru, capital_en). The region is the capital's
# first-level administrative division; for the many countries whose capital *is* its own first-level
# unit (capital district, governorate or city-state) the two names coincide.
COUNTRIES = [
    # -- Europe ------------------------------------------------------------
    ("Австрия", "Austria", "Вена", "Vienna", "Вена", "Vienna"),
    ("Албания", "Albania", "Тирана", "Tirana", "Тирана", "Tirana"),
    ("Андорра", "Andorra", "Андорра-ла-Велья", "Andorra la Vella", "Андорра-ла-Велья", "Andorra la Vella"),
    ("Бельгия", "Belgium", "Брюссельский столичный регион", "Brussels-Capital Region", "Брюссель", "Brussels"),
    ("Болгария", "Bulgaria", "София", "Sofia", "София", "Sofia"),
    ("Босния и Герцеговина", "Bosnia and Herzegovina", "Сараево", "Sarajevo", "Сараево", "Sarajevo"),
    ("Ватикан", "Vatican City", "Ватикан", "Vatican City", "Ватикан", "Vatican City"),
    ("Греция", "Greece", "Аттика", "Attica", "Афины", "Athens"),
    ("Ирландия", "Ireland", "Ленстер", "Leinster", "Дублин", "Dublin"),
    ("Латвия", "Latvia", "Рига", "Riga", "Рига", "Riga"),
    ("Лихтенштейн", "Liechtenstein", "Вадуц", "Vaduz", "Вадуц", "Vaduz"),
    ("Люксембург", "Luxembourg", "Люксембург", "Luxembourg", "Люксембург", "Luxembourg"),
    ("Мальта", "Malta", "Валлетта", "Valletta", "Валлетта", "Valletta"),
    ("Молдавия", "Moldova", "Кишинёв", "Chisinau", "Кишинёв", "Chisinau"),
    ("Монако", "Monaco", "Монако", "Monaco", "Монако", "Monaco"),
    ("Норвегия", "Norway", "Осло", "Oslo", "Осло", "Oslo"),
    ("Португалия", "Portugal", "Лиссабон", "Lisbon", "Лиссабон", "Lisbon"),
    ("Румыния", "Romania", "Бухарест", "Bucharest", "Бухарест", "Bucharest"),
    ("Сан-Марино", "San Marino", "Сан-Марино", "San Marino", "Сан-Марино", "San Marino"),
    ("Сербия", "Serbia", "Белград", "Belgrade", "Белград", "Belgrade"),
    ("Словения", "Slovenia", "Люблянский регион", "Central Slovenia", "Любляна", "Ljubljana"),
    ("Украина", "Ukraine", "Киев", "Kyiv", "Киев", "Kyiv"),
    ("Франция", "France", "Иль-де-Франс", "Ile-de-France", "Париж", "Paris"),
    ("Хорватия", "Croatia", "Загреб", "Zagreb", "Загреб", "Zagreb"),
    ("Черногория", "Montenegro", "Подгорица", "Podgorica", "Подгорица", "Podgorica"),
    ("Швеция", "Sweden", "Стокгольм", "Stockholm", "Стокгольм", "Stockholm"),
    ("Эстония", "Estonia", "Харьюмаа", "Harju County", "Таллин", "Tallinn"),
    # -- Asia --------------------------------------------------------------
    ("Азербайджан", "Azerbaijan", "Баку", "Baku", "Баку", "Baku"),
    ("Афганистан", "Afghanistan", "Кабул", "Kabul", "Кабул", "Kabul"),
    ("Бангладеш", "Bangladesh", "Дакка", "Dhaka", "Дакка", "Dhaka"),
    ("Бахрейн", "Bahrain", "Манама", "Manama", "Манама", "Manama"),
    ("Бруней", "Brunei", "Бруней-Муара", "Brunei-Muara", "Бандар-Сери-Бегаван", "Bandar Seri Begawan"),
    ("Бутан", "Bhutan", "Тхимпху", "Thimphu", "Тхимпху", "Thimphu"),
    ("Восточный Тимор", "Timor-Leste", "Дили", "Dili", "Дили", "Dili"),
    ("Вьетнам", "Vietnam", "Ханой", "Hanoi", "Ханой", "Hanoi"),
    ("Израиль", "Israel", "Иерусалим", "Jerusalem", "Иерусалим", "Jerusalem"),
    ("Индия", "India", "Дели", "Delhi", "Нью-Дели", "New Delhi"),
    ("Индонезия", "Indonesia", "Джакарта", "Jakarta", "Джакарта", "Jakarta"),
    ("Иордания", "Jordan", "Амман", "Amman", "Амман", "Amman"),
    ("Ирак", "Iraq", "Багдад", "Baghdad", "Багдад", "Baghdad"),
    ("Иран", "Iran", "Тегеран", "Tehran", "Тегеран", "Tehran"),
    ("Йемен", "Yemen", "Сана", "Sanaa", "Сана", "Sanaa"),
    ("Камбоджа", "Cambodia", "Пномпень", "Phnom Penh", "Пномпень", "Phnom Penh"),
    ("Катар", "Qatar", "Доха", "Doha", "Доха", "Doha"),
    ("КНДР", "North Korea", "Пхеньян", "Pyongyang", "Пхеньян", "Pyongyang"),
    ("Республика Корея", "South Korea", "Сеул", "Seoul", "Сеул", "Seoul"),
    ("Кувейт", "Kuwait", "Эль-Асима", "Al Asimah", "Эль-Кувейт", "Kuwait City"),
    ("Лаос", "Laos", "Вьентьян", "Vientiane", "Вьентьян", "Vientiane"),
    ("Ливан", "Lebanon", "Бейрут", "Beirut", "Бейрут", "Beirut"),
    ("Малайзия", "Malaysia", "Куала-Лумпур", "Kuala Lumpur", "Куала-Лумпур", "Kuala Lumpur"),
    ("Мальдивы", "Maldives", "Мале", "Male", "Мале", "Male"),
    ("Монголия", "Mongolia", "Улан-Батор", "Ulaanbaatar", "Улан-Батор", "Ulaanbaatar"),
    ("Мьянма", "Myanmar", "Нейпьидо", "Naypyidaw", "Нейпьидо", "Naypyidaw"),
    ("Непал", "Nepal", "Багмати", "Bagmati", "Катманду", "Kathmandu"),
    ("ОАЭ", "United Arab Emirates", "Абу-Даби", "Abu Dhabi", "Абу-Даби", "Abu Dhabi"),
    ("Оман", "Oman", "Маскат", "Muscat", "Маскат", "Muscat"),
    ("Пакистан", "Pakistan", "Исламабад", "Islamabad", "Исламабад", "Islamabad"),
    ("Саудовская Аравия", "Saudi Arabia", "Эр-Рияд", "Riyadh", "Эр-Рияд", "Riyadh"),
    ("Сингапур", "Singapore", "Сингапур", "Singapore", "Сингапур", "Singapore"),
    ("Сирия", "Syria", "Дамаск", "Damascus", "Дамаск", "Damascus"),
    ("Таджикистан", "Tajikistan", "Душанбе", "Dushanbe", "Душанбе", "Dushanbe"),
    ("Таиланд", "Thailand", "Бангкок", "Bangkok", "Бангкок", "Bangkok"),
    ("Туркмения", "Turkmenistan", "Ашхабад", "Ashgabat", "Ашхабад", "Ashgabat"),
    ("Филиппины", "Philippines", "Столичный регион", "Metro Manila", "Манила", "Manila"),
    ("Шри-Ланка", "Sri Lanka", "Западная провинция", "Western Province", "Коломбо", "Colombo"),
    ("Япония", "Japan", "Токио", "Tokyo", "Токио", "Tokyo"),
    # -- Africa ------------------------------------------------------------
    ("Алжир", "Algeria", "Алжир", "Algiers", "Алжир", "Algiers"),
    ("Ангола", "Angola", "Луанда", "Luanda", "Луанда", "Luanda"),
    ("Бенин", "Benin", "Уэме", "Oueme", "Порто-Ново", "Porto-Novo"),
    ("Ботсвана", "Botswana", "Габороне", "Gaborone", "Габороне", "Gaborone"),
    ("Буркина-Фасо", "Burkina Faso", "Кадиого", "Kadiogo", "Уагадугу", "Ouagadougou"),
    ("Бурунди", "Burundi", "Гитега", "Gitega", "Гитега", "Gitega"),
    ("Габон", "Gabon", "Эстуарий", "Estuaire", "Либревиль", "Libreville"),
    ("Гамбия", "Gambia", "Банжул", "Banjul", "Банжул", "Banjul"),
    ("Гана", "Ghana", "Большая Аккра", "Greater Accra", "Аккра", "Accra"),
    ("Гвинея", "Guinea", "Конакри", "Conakry", "Конакри", "Conakry"),
    ("Гвинея-Бисау", "Guinea-Bissau", "Бисау", "Bissau", "Бисау", "Bissau"),
    ("Джибути", "Djibouti", "Джибути", "Djibouti", "Джибути", "Djibouti"),
    ("Замбия", "Zambia", "Лусака", "Lusaka", "Лусака", "Lusaka"),
    ("Зимбабве", "Zimbabwe", "Хараре", "Harare", "Хараре", "Harare"),
    ("Кабо-Верде", "Cabo Verde", "Прая", "Praia", "Прая", "Praia"),
    ("Камерун", "Cameroon", "Центральный регион", "Centre Region", "Яунде", "Yaounde"),
    ("Кения", "Kenya", "Найроби", "Nairobi", "Найроби", "Nairobi"),
    ("Коморы", "Comoros", "Гранд-Комор", "Grande Comore", "Морони", "Moroni"),
    ("Республика Конго", "Republic of the Congo", "Браззавиль", "Brazzaville", "Браззавиль", "Brazzaville"),
    ("ДР Конго", "DR Congo", "Киншаса", "Kinshasa", "Киншаса", "Kinshasa"),
    ("Кот-д'Ивуар", "Cote d'Ivoire", "Ямусукро", "Yamoussoukro", "Ямусукро", "Yamoussoukro"),
    ("Лесото", "Lesotho", "Масеру", "Maseru", "Масеру", "Maseru"),
    ("Либерия", "Liberia", "Монтсеррадо", "Montserrado", "Монровия", "Monrovia"),
    ("Ливия", "Libya", "Триполи", "Tripoli", "Триполи", "Tripoli"),
    ("Маврикий", "Mauritius", "Порт-Луи", "Port Louis", "Порт-Луи", "Port Louis"),
    ("Мавритания", "Mauritania", "Нуакшот", "Nouakchott", "Нуакшот", "Nouakchott"),
    ("Мадагаскар", "Madagascar", "Аналаманга", "Analamanga", "Антананариву", "Antananarivo"),
    ("Малави", "Malawi", "Лилонгве", "Lilongwe", "Лилонгве", "Lilongwe"),
    ("Мали", "Mali", "Бамако", "Bamako", "Бамако", "Bamako"),
    ("Марокко", "Morocco", "Рабат-Сале-Кенитра", "Rabat-Sale-Kenitra", "Рабат", "Rabat"),
    ("Мозамбик", "Mozambique", "Мапуту", "Maputo", "Мапуту", "Maputo"),
    ("Намибия", "Namibia", "Кхомас", "Khomas", "Виндхук", "Windhoek"),
    ("Нигер", "Niger", "Ниамей", "Niamey", "Ниамей", "Niamey"),
    ("Нигерия", "Nigeria", "Федеральная столичная территория", "Federal Capital Territory", "Абуджа", "Abuja"),
    ("Руанда", "Rwanda", "Кигали", "Kigali", "Кигали", "Kigali"),
    ("Сан-Томе и Принсипи", "Sao Tome and Principe", "Сан-Томе", "Sao Tome", "Сан-Томе", "Sao Tome"),
    ("Сейшелы", "Seychelles", "Маэ", "Mahe", "Виктория", "Victoria"),
    ("Сенегал", "Senegal", "Дакар", "Dakar", "Дакар", "Dakar"),
    ("Сомали", "Somalia", "Банадир", "Banaadir", "Могадишо", "Mogadishu"),
    ("Судан", "Sudan", "Хартум", "Khartoum", "Хартум", "Khartoum"),
    ("Южный Судан", "South Sudan", "Центральная Экватория", "Central Equatoria", "Джуба", "Juba"),
    ("Сьерра-Леоне", "Sierra Leone", "Западная область", "Western Area", "Фритаун", "Freetown"),
    ("Танзания", "Tanzania", "Додома", "Dodoma", "Додома", "Dodoma"),
    ("Того", "Togo", "Приморская область", "Maritime Region", "Ломе", "Lome"),
    ("Тунис", "Tunisia", "Тунис", "Tunis", "Тунис", "Tunis"),
    ("Уганда", "Uganda", "Кампала", "Kampala", "Кампала", "Kampala"),
    ("ЦАР", "Central African Republic", "Банги", "Bangui", "Банги", "Bangui"),
    ("Чад", "Chad", "Нджамена", "N'Djamena", "Нджамена", "N'Djamena"),
    ("Экваториальная Гвинея", "Equatorial Guinea", "Биоко-Норте", "Bioko Norte", "Малабо", "Malabo"),
    ("Эритрея", "Eritrea", "Маакель", "Maekel", "Асмэра", "Asmara"),
    ("Эсватини", "Eswatini", "Хохо", "Hhohho", "Мбабане", "Mbabane"),
    ("Эфиопия", "Ethiopia", "Аддис-Абеба", "Addis Ababa", "Аддис-Абеба", "Addis Ababa"),
    # -- Americas ----------------------------------------------------------
    ("Антигуа и Барбуда", "Antigua and Barbuda", "Сент-Джон", "Saint John", "Сент-Джонс", "Saint John's"),
    ("Аргентина", "Argentina", "Буэнос-Айрес", "Buenos Aires", "Буэнос-Айрес", "Buenos Aires"),
    ("Багамы", "Bahamas", "Нью-Провиденс", "New Providence", "Нассау", "Nassau"),
    ("Барбадос", "Barbados", "Сент-Майкл", "Saint Michael", "Бриджтаун", "Bridgetown"),
    ("Белиз", "Belize", "Кайо", "Cayo", "Бельмопан", "Belmopan"),
    ("Боливия", "Bolivia", "Чукисака", "Chuquisaca", "Сукре", "Sucre"),
    ("Венесуэла", "Venezuela", "Столичный округ", "Capital District", "Каракас", "Caracas"),
    ("Гаити", "Haiti", "Западный департамент", "Ouest", "Порт-о-Пренс", "Port-au-Prince"),
    ("Гайана", "Guyana", "Демерара-Махайка", "Demerara-Mahaica", "Джорджтаун", "Georgetown"),
    ("Гватемала", "Guatemala", "Гватемала", "Guatemala", "Гватемала", "Guatemala City"),
    ("Гондурас", "Honduras", "Франсиско-Морасан", "Francisco Morazan", "Тегусигальпа", "Tegucigalpa"),
    ("Гренада", "Grenada", "Сент-Джордж", "Saint George", "Сент-Джорджес", "St. George's"),
    ("Доминика", "Dominica", "Сент-Джордж", "Saint George", "Розо", "Roseau"),
    (
        "Доминиканская Республика",
        "Dominican Republic",
        "Национальный округ",
        "Distrito Nacional",
        "Санто-Доминго",
        "Santo Domingo",
    ),
    ("Канада", "Canada", "Онтарио", "Ontario", "Оттава", "Ottawa"),
    ("Колумбия", "Colombia", "Столичный округ Богота", "Bogota Capital District", "Богота", "Bogota"),
    ("Коста-Рика", "Costa Rica", "Сан-Хосе", "San Jose", "Сан-Хосе", "San Jose"),
    ("Куба", "Cuba", "Гавана", "Havana", "Гавана", "Havana"),
    ("Мексика", "Mexico", "Мехико", "Mexico City", "Мехико", "Mexico City"),
    ("Никарагуа", "Nicaragua", "Манагуа", "Managua", "Манагуа", "Managua"),
    ("Панама", "Panama", "Панама", "Panama", "Панама", "Panama City"),
    ("Парагвай", "Paraguay", "Асунсьон", "Asuncion", "Асунсьон", "Asuncion"),
    ("Перу", "Peru", "Лима", "Lima", "Лима", "Lima"),
    ("Сальвадор", "El Salvador", "Сан-Сальвадор", "San Salvador", "Сан-Сальвадор", "San Salvador"),
    (
        "Сент-Винсент и Гренадины",
        "Saint Vincent and the Grenadines",
        "Сент-Джордж",
        "Saint George",
        "Кингстаун",
        "Kingstown",
    ),
    (
        "Сент-Китс и Невис",
        "Saint Kitts and Nevis",
        "Сент-Джордж-Бассетер",
        "Saint George Basseterre",
        "Бастер",
        "Basseterre",
    ),
    ("Сент-Люсия", "Saint Lucia", "Кастри", "Castries", "Кастри", "Castries"),
    ("Суринам", "Suriname", "Парамарибо", "Paramaribo", "Парамарибо", "Paramaribo"),
    ("Тринидад и Тобаго", "Trinidad and Tobago", "Порт-оф-Спейн", "Port of Spain", "Порт-оф-Спейн", "Port of Spain"),
    ("Уругвай", "Uruguay", "Монтевидео", "Montevideo", "Монтевидео", "Montevideo"),
    ("Чили", "Chile", "Столичная область", "Santiago Metropolitan", "Сантьяго", "Santiago"),
    ("Эквадор", "Ecuador", "Пичинча", "Pichincha", "Кито", "Quito"),
    ("Ямайка", "Jamaica", "Суррей", "Surrey", "Кингстон", "Kingston"),
    # -- Oceania -----------------------------------------------------------
    ("Вануату", "Vanuatu", "Шефа", "Shefa", "Порт-Вила", "Port Vila"),
    ("Кирибати", "Kiribati", "Тарава", "Tarawa", "Южная Тарава", "South Tarawa"),
    ("Маршалловы Острова", "Marshall Islands", "Маджуро", "Majuro", "Маджуро", "Majuro"),
    ("Микронезия", "Micronesia", "Понпеи", "Pohnpei", "Паликир", "Palikir"),
    ("Науру", "Nauru", "Ярен", "Yaren", "Ярен", "Yaren"),
    ("Новая Зеландия", "New Zealand", "Веллингтон", "Wellington", "Веллингтон", "Wellington"),
    ("Палау", "Palau", "Мелекеок", "Melekeok", "Нгерулмуд", "Ngerulmud"),
    (
        "Папуа — Новая Гвинея",
        "Papua New Guinea",
        "Национальный столичный округ",
        "National Capital District",
        "Порт-Морсби",
        "Port Moresby",
    ),
    ("Самоа", "Samoa", "Туамасага", "Tuamasaga", "Апиа", "Apia"),
    ("Соломоновы Острова", "Solomon Islands", "Гуадалканал", "Guadalcanal", "Хониара", "Honiara"),
    ("Тонга", "Tonga", "Тонгатапу", "Tongatapu", "Нукуалофа", "Nuku'alofa"),
    ("Тувалу", "Tuvalu", "Фунафути", "Funafuti", "Фунафути", "Funafuti"),
    ("Фиджи", "Fiji", "Центральный округ", "Central Division", "Сува", "Suva"),
]


def _siblings(parent):
    """The parent's children by path range: ``get_children()`` returns nothing on a drifted
    ``numchild``, which would hide an existing child and add a second one."""
    from locations.models import Location

    return Location.objects.filter(
        depth=parent.depth + 1, path__range=Location._get_children_path_interval(parent.path)
    )


def _child(parent, names, sort_order, *, hidden=False):
    """The parent's child with this Russian name, appended when absent, live namesakes preferred."""
    from locations.models import add_location_child

    ru, kk, en = names
    existing = _siblings(parent).filter(name_ru=ru).order_by("is_deleted", "path").first()
    if existing is not None:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.save(update_fields=["is_deleted"])
        return existing
    return add_location_child(
        parent, name=ru, name_ru=ru, name_kk=kk, name_en=en, sort_order=sort_order, is_hidden=hidden
    )


def _add_city(region, names, sort_order, *, hidden=False):
    from locations.models import LocationFallback

    city = _child(region, names, sort_order, hidden=hidden)
    if not LocationFallback.objects.filter(city=city).exists():
        venue = _child(city, _OTHER_VENUE, 9999, hidden=True)
        LocationFallback.objects.get_or_create(city=city, defaults={"location": venue})
    return city


def add_countries(apps, schema_editor):
    from locations.models import Location, add_location_child

    # New countries sort after the ones already ordered by 0014 but before the catch-all at 9999.
    used = [node.sort_order for node in Location.objects.filter(depth=1, is_deleted=False) if node.sort_order < 9999]
    order = max(used) + 1 if used else 1

    for country_ru, country_en, region_ru, region_en, capital_ru, capital_en in COUNTRIES:
        country = Location.objects.filter(depth=1, name_ru=country_ru).order_by("is_deleted", "path").first()
        if country is None:
            country = add_location_child(
                None, name=country_ru, name_ru=country_ru, name_kk=country_ru, name_en=country_en, sort_order=order
            )
            order += 1
        elif country.is_deleted:
            country.is_deleted = False
            country.save(update_fields=["is_deleted"])

        region = _child(country, (region_ru, region_ru, region_en), 1)
        _add_city(region, (capital_ru, capital_ru, capital_en), 1)
        _add_city(region, _OTHER_CITY, 9999, hidden=True)
        _child(country, _OTHER_REGION, 9999, hidden=True)


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0014_capitals_and_sort_order"),
    ]

    operations = [
        migrations.RunPython(add_countries, migrations.RunPython.noop),
    ]
