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
    # -- Already seeded by 0013; listed so their coordinates get filled in too ----------------
    ("Беларусь", "Belarus", "Минск", "Minsk", "Минск", "Minsk"),
    ("Грузия", "Georgia", "Тбилиси", "Tbilisi", "Тбилиси", "Tbilisi"),
    ("Армения", "Armenia", "Ереван", "Yerevan", "Ереван", "Yerevan"),
    ("Узбекистан", "Uzbekistan", "Ташкент", "Tashkent", "Ташкент", "Tashkent"),
    ("Турция", "Turkey", "Анкара", "Ankara", "Анкара", "Ankara"),
    ("Литва", "Lithuania", "Вильнюсский уезд", "Vilnius County", "Вильнюс", "Vilnius"),
    ("Польша", "Poland", "Мазовецкое воеводство", "Masovian Voivodeship", "Варшава", "Warsaw"),
    ("Чехия", "Czech Republic", "Прага", "Prague", "Прага", "Prague"),
    ("Словакия", "Slovakia", "Братиславский край", "Bratislava Region", "Братислава", "Bratislava"),
    ("Венгрия", "Hungary", "Будапешт", "Budapest", "Будапешт", "Budapest"),
    ("Германия", "Germany", "Берлин", "Berlin", "Берлин", "Berlin"),
    ("Нидерланды", "Netherlands", "Северная Голландия", "North Holland", "Амстердам", "Amsterdam"),
    ("Дания", "Denmark", "Столичная область", "Capital Region", "Копенгаген", "Copenhagen"),
    ("Финляндия", "Finland", "Уусимаа", "Uusimaa", "Хельсинки", "Helsinki"),
    ("Исландия", "Iceland", "Столичный регион", "Capital Region", "Рейкьявик", "Reykjavik"),
    ("Великобритания", "United Kingdom", "Англия", "England", "Лондон", "London"),
    ("Швейцария", "Switzerland", "Берн", "Bern", "Берн", "Bern"),
    ("Италия", "Italy", "Лацио", "Lazio", "Рим", "Rome"),
    ("Испания", "Spain", "Мадрид", "Community of Madrid", "Мадрид", "Madrid"),
    ("Северная Македония", "North Macedonia", "Скопье", "Skopje", "Скопье", "Skopje"),
    ("Кипр", "Cyprus", "Никосия", "Nicosia", "Никосия", "Nicosia"),
    ("Египет", "Egypt", "Каир", "Cairo", "Каир", "Cairo"),
    ("ЮАР", "South Africa", "Гаутенг", "Gauteng", "Претория", "Pretoria"),
    ("США", "United States", "Округ Колумбия", "District of Columbia", "Вашингтон", "Washington"),
    ("Бразилия", "Brazil", "Федеральный округ", "Federal District", "Бразилиа", "Brasilia"),
    (
        "Австралия",
        "Australia",
        "Австралийская столичная территория",
        "Australian Capital Territory",
        "Канберра",
        "Canberra",
    ),
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

# Capital coordinates, used for the country, its capital's region and the capital itself: the
# map only plots nodes that have them, and the cascade sinks the ones that do not.
CAPITAL_COORDS = {
    # The countries seeded by 0013 were created without coordinates; filled in here too.
    "Беларусь": (53.9, 27.57),
    "Грузия": (41.72, 44.79),
    "Армения": (40.18, 44.51),
    "Узбекистан": (41.31, 69.24),
    "Турция": (39.93, 32.86),
    "Литва": (54.69, 25.28),
    "Польша": (52.23, 21.01),
    "Чехия": (50.08, 14.44),
    "Словакия": (48.15, 17.11),
    "Венгрия": (47.5, 19.04),
    "Германия": (52.52, 13.4),
    "Нидерланды": (52.37, 4.9),
    "Дания": (55.68, 12.57),
    "Финляндия": (60.17, 24.94),
    "Исландия": (64.15, -21.94),
    "Великобритания": (51.51, -0.13),
    "Швейцария": (46.95, 7.45),
    "Италия": (41.9, 12.5),
    "Испания": (40.42, -3.7),
    "Северная Македония": (41.99, 21.43),
    "Кипр": (35.19, 33.38),
    "Египет": (30.04, 31.24),
    "ЮАР": (-25.75, 28.19),
    "США": (38.9, -77.04),
    "Бразилия": (-15.79, -47.88),
    "Австралия": (-35.28, 149.13),
    "Австрия": (48.21, 16.37),
    "Албания": (41.33, 19.82),
    "Андорра": (42.51, 1.52),
    "Бельгия": (50.85, 4.35),
    "Болгария": (42.7, 23.32),
    "Босния и Герцеговина": (43.86, 18.41),
    "Ватикан": (41.9, 12.45),
    "Греция": (37.98, 23.73),
    "Ирландия": (53.35, -6.26),
    "Латвия": (56.95, 24.11),
    "Лихтенштейн": (47.14, 9.52),
    "Люксембург": (49.61, 6.13),
    "Мальта": (35.9, 14.51),
    "Молдавия": (47.01, 28.86),
    "Монако": (43.73, 7.42),
    "Норвегия": (59.91, 10.75),
    "Португалия": (38.72, -9.14),
    "Румыния": (44.43, 26.1),
    "Сан-Марино": (43.94, 12.45),
    "Сербия": (44.79, 20.45),
    "Словения": (46.06, 14.51),
    "Украина": (50.45, 30.52),
    "Франция": (48.86, 2.35),
    "Хорватия": (45.81, 15.98),
    "Черногория": (42.44, 19.26),
    "Швеция": (59.33, 18.07),
    "Эстония": (59.44, 24.75),
    "Азербайджан": (40.41, 49.87),
    "Афганистан": (34.53, 69.17),
    "Бангладеш": (23.81, 90.41),
    "Бахрейн": (26.23, 50.59),
    "Бруней": (4.9, 114.94),
    "Бутан": (27.47, 89.64),
    "Восточный Тимор": (-8.56, 125.56),
    "Вьетнам": (21.03, 105.85),
    "Израиль": (31.77, 35.21),
    "Индия": (28.61, 77.21),
    "Индонезия": (-6.21, 106.85),
    "Иордания": (31.95, 35.93),
    "Ирак": (33.31, 44.36),
    "Иран": (35.69, 51.39),
    "Йемен": (15.37, 44.19),
    "Камбоджа": (11.56, 104.92),
    "Катар": (25.29, 51.53),
    "КНДР": (39.04, 125.76),
    "Республика Корея": (37.57, 126.98),
    "Кувейт": (29.38, 47.99),
    "Лаос": (17.97, 102.63),
    "Ливан": (33.89, 35.5),
    "Малайзия": (3.14, 101.69),
    "Мальдивы": (4.18, 73.51),
    "Монголия": (47.89, 106.91),
    "Мьянма": (19.75, 96.1),
    "Непал": (27.72, 85.32),
    "ОАЭ": (24.45, 54.38),
    "Оман": (23.59, 58.41),
    "Пакистан": (33.68, 73.05),
    "Саудовская Аравия": (24.71, 46.68),
    "Сингапур": (1.35, 103.82),
    "Сирия": (33.51, 36.28),
    "Таджикистан": (38.56, 68.79),
    "Таиланд": (13.76, 100.5),
    "Туркмения": (37.96, 58.33),
    "Филиппины": (14.6, 120.98),
    "Шри-Ланка": (6.93, 79.86),
    "Япония": (35.68, 139.69),
    "Алжир": (36.75, 3.06),
    "Ангола": (-8.84, 13.23),
    "Бенин": (6.5, 2.62),
    "Ботсвана": (-24.63, 25.92),
    "Буркина-Фасо": (12.37, -1.52),
    "Бурунди": (-3.43, 29.93),
    "Габон": (0.42, 9.47),
    "Гамбия": (13.45, -16.58),
    "Гана": (5.6, -0.19),
    "Гвинея": (9.64, -13.58),
    "Гвинея-Бисау": (11.86, -15.6),
    "Джибути": (11.59, 43.15),
    "Замбия": (-15.39, 28.32),
    "Зимбабве": (-17.83, 31.05),
    "Кабо-Верде": (14.93, -23.51),
    "Камерун": (3.85, 11.5),
    "Кения": (-1.29, 36.82),
    "Коморы": (-11.7, 43.26),
    "Республика Конго": (-4.26, 15.28),
    "ДР Конго": (-4.44, 15.27),
    "Кот-д'Ивуар": (6.83, -5.29),
    "Лесото": (-29.31, 27.48),
    "Либерия": (6.3, -10.8),
    "Ливия": (32.89, 13.19),
    "Маврикий": (-20.16, 57.5),
    "Мавритания": (18.08, -15.98),
    "Мадагаскар": (-18.88, 47.51),
    "Малави": (-13.96, 33.79),
    "Мали": (12.64, -8.0),
    "Марокко": (34.02, -6.84),
    "Мозамбик": (-25.97, 32.58),
    "Намибия": (-22.56, 17.08),
    "Нигер": (13.51, 2.11),
    "Нигерия": (9.06, 7.49),
    "Руанда": (-1.94, 30.06),
    "Сан-Томе и Принсипи": (0.34, 6.73),
    "Сейшелы": (-4.62, 55.45),
    "Сенегал": (14.72, -17.47),
    "Сомали": (2.05, 45.32),
    "Судан": (15.5, 32.56),
    "Южный Судан": (4.85, 31.58),
    "Сьерра-Леоне": (8.48, -13.23),
    "Танзания": (-6.16, 35.75),
    "Того": (6.13, 1.22),
    "Тунис": (36.81, 10.18),
    "Уганда": (0.35, 32.58),
    "ЦАР": (4.39, 18.56),
    "Чад": (12.13, 15.06),
    "Экваториальная Гвинея": (3.75, 8.78),
    "Эритрея": (15.34, 38.93),
    "Эсватини": (-26.32, 31.14),
    "Эфиопия": (9.01, 38.76),
    "Антигуа и Барбуда": (17.12, -61.85),
    "Аргентина": (-34.6, -58.38),
    "Багамы": (25.06, -77.34),
    "Барбадос": (13.1, -59.61),
    "Белиз": (17.25, -88.77),
    "Боливия": (-19.03, -65.26),
    "Венесуэла": (10.48, -66.9),
    "Гаити": (18.59, -72.31),
    "Гайана": (6.8, -58.16),
    "Гватемала": (14.63, -90.51),
    "Гондурас": (14.07, -87.19),
    "Гренада": (12.06, -61.75),
    "Доминика": (15.3, -61.39),
    "Доминиканская Республика": (18.49, -69.93),
    "Канада": (45.42, -75.7),
    "Колумбия": (4.71, -74.07),
    "Коста-Рика": (9.93, -84.08),
    "Куба": (23.11, -82.37),
    "Мексика": (19.43, -99.13),
    "Никарагуа": (12.11, -86.24),
    "Панама": (8.98, -79.52),
    "Парагвай": (-25.28, -57.64),
    "Перу": (-12.05, -77.04),
    "Сальвадор": (13.69, -89.19),
    "Сент-Винсент и Гренадины": (13.16, -61.22),
    "Сент-Китс и Невис": (17.3, -62.72),
    "Сент-Люсия": (14.01, -60.99),
    "Суринам": (5.85, -55.2),
    "Тринидад и Тобаго": (10.65, -61.51),
    "Уругвай": (-34.9, -56.16),
    "Чили": (-33.45, -70.67),
    "Эквадор": (-0.18, -78.47),
    "Ямайка": (17.97, -76.79),
    "Вануату": (-17.73, 168.32),
    "Кирибати": (1.33, 172.98),
    "Маршалловы Острова": (7.09, 171.38),
    "Микронезия": (6.92, 158.16),
    "Науру": (-0.55, 166.92),
    "Новая Зеландия": (-41.29, 174.78),
    "Палау": (7.5, 134.62),
    "Папуа — Новая Гвинея": (-9.44, 147.18),
    "Самоа": (-13.83, -171.77),
    "Соломоновы Острова": (-9.43, 159.95),
    "Тонга": (-21.14, -175.2),
    "Тувалу": (-8.52, 179.19),
    "Фиджи": (-18.14, 178.44),
}


def _siblings(parent):
    """The parent's children by path range: ``get_children()`` returns nothing on a drifted
    ``numchild``, which would hide an existing child and add a second one."""
    from locations.models import Location

    return Location.objects.filter(
        depth=parent.depth + 1, path__range=Location._get_children_path_interval(parent.path)
    )


def _refresh(node, coords):
    """Undelete a node and fill in coordinates it is missing, without overwriting a real value."""
    fields = []
    if node.is_deleted:
        node.is_deleted = False
        fields.append("is_deleted")
    if coords and node.lat is None and node.lng is None:
        node.lat, node.lng = coords
        fields += ["lat", "lng"]
    if fields:
        node.save(update_fields=fields)
    return node


def _child(parent, names, sort_order, *, hidden=False, coords=None):
    """The parent's child with this Russian name, appended when absent, live namesakes preferred."""
    from locations.models import add_location_child

    ru, kk, en = names
    existing = _siblings(parent).filter(name_ru=ru).order_by("is_deleted", "path").first()
    if existing is not None:
        return _refresh(existing, coords)
    lat, lng = coords or (None, None)
    return add_location_child(
        parent,
        name=ru,
        name_ru=ru,
        name_kk=kk,
        name_en=en,
        sort_order=sort_order,
        is_hidden=hidden,
        lat=lat,
        lng=lng,
    )


def _add_city(region, names, sort_order, *, hidden=False, coords=None):
    from locations.models import LocationFallback

    city = _child(region, names, sort_order, hidden=hidden, coords=coords)
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
        coords = CAPITAL_COORDS.get(country_ru)
        lat, lng = coords or (None, None)
        country = Location.objects.filter(depth=1, name_ru=country_ru).order_by("is_deleted", "path").first()
        if country is None:
            country = add_location_child(
                None,
                name=country_ru,
                name_ru=country_ru,
                name_kk=country_ru,
                name_en=country_en,
                sort_order=order,
                lat=lat,
                lng=lng,
            )
            order += 1
        else:
            _refresh(country, coords)

        region = _child(country, (region_ru, region_ru, region_en), 1, coords=coords)
        _add_city(region, (capital_ru, capital_ru, capital_en), 1, coords=coords)
        _add_city(region, _OTHER_CITY, 9999, hidden=True)
        _add_city(_child(country, _OTHER_REGION, 9999, hidden=True), _OTHER_CITY, 9999, hidden=True)

    # The catch-alls seeded long ago (0004/0006/0007) were left visible; production hid them by hand,
    # so a fresh database would otherwise offer "Другой город" as an ordinary pickable city.
    Location.objects.filter(depth__in=[2, 3], is_hidden=False, name_ru__in=("Другой регион", "Другой город")).update(
        is_hidden=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0014_capitals_and_sort_order"),
    ]

    operations = [
        migrations.RunPython(add_countries, migrations.RunPython.noop),
    ]
