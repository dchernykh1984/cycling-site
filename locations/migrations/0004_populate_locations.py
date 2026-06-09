"""
Populate the 4-level Location tree:
  depth=1  Country
  depth=2  Region / oblast / city-of-republican-significance
  depth=3  City        (+ "Другой город" as last entry)
  depth=4  Venue       (only "Другая локация" is_hidden=True created here;
                        real venues are added by admins later)

Every region ends with "Другой город", every city has one hidden
"Другая локация" child.  Every country ends with "Другой регион" which
already has "Другой город" → "Другая локация" beneath it.
"Другая страна" is the global catch-all country.
"""

from django.db import migrations

# ---------------------------------------------------------------------------
# Location data
# ---------------------------------------------------------------------------

_OTHER = {
    "region": {"ru": "Другой регион", "kk": "Басқа аймақ", "en": "Other region"},
    "city": {"ru": "Другой город", "kk": "Басқа қала", "en": "Other city"},
    "venue": {"ru": "Другая локация", "kk": "Басқа орын", "en": "Other location"},
}

LOCATION_DATA = [
    # -----------------------------------------------------------------------
    # Kazakhstan
    # -----------------------------------------------------------------------
    {
        "ru": "Казахстан",
        "kk": "Қазақстан",
        "en": "Kazakhstan",
        "so": 1,
        "regions": [
            {
                "ru": "Алматы",
                "kk": "Алматы",
                "en": "Almaty",
                "so": 1,
                "cities": [
                    {"ru": "Алматы", "kk": "Алматы", "en": "Almaty", "so": 1},
                ],
            },
            {
                "ru": "Астана",
                "kk": "Астана",
                "en": "Astana",
                "so": 2,
                "cities": [
                    {"ru": "Астана", "kk": "Астана", "en": "Astana", "so": 1},
                ],
            },
            {
                "ru": "Шымкент",
                "kk": "Шымкент",
                "en": "Shymkent",
                "so": 3,
                "cities": [
                    {"ru": "Шымкент", "kk": "Шымкент", "en": "Shymkent", "so": 1},
                ],
            },
            {
                "ru": "Алматинская область",
                "kk": "Алматы облысы",
                "en": "Almaty Region",
                "so": 4,
                "cities": [
                    {"ru": "Конаев", "kk": "Қонаев", "en": "Konayev", "so": 1},
                    {"ru": "Каскелен", "kk": "Қаскелен", "en": "Kaskelen", "so": 2},
                    {"ru": "Талгар", "kk": "Талғар", "en": "Talgar", "so": 3},
                    {"ru": "Есик", "kk": "Есік", "en": "Esik", "so": 4},
                    {"ru": "Ұзынағаш", "kk": "Ұзынағаш", "en": "Uzunagach", "so": 5},
                ],
            },
            {
                "ru": "Жетысуская область",
                "kk": "Жетісу облысы",
                "en": "Zhetisu Region",
                "so": 5,
                "cities": [
                    {"ru": "Талдыкорган", "kk": "Талдықорған", "en": "Taldykorgan", "so": 1},
                    {"ru": "Текели", "kk": "Текелі", "en": "Tekeli", "so": 2},
                    {"ru": "Жаркент", "kk": "Жаркент", "en": "Zharkent", "so": 3},
                    {"ru": "Сарқан", "kk": "Сарқан", "en": "Sarqan", "so": 4},
                    {"ru": "Ұштөбе", "kk": "Ұштөбе", "en": "Ushtobe", "so": 5},
                ],
            },
            {
                "ru": "Жамбылская область",
                "kk": "Жамбыл облысы",
                "en": "Zhambyl Region",
                "so": 6,
                "cities": [
                    {"ru": "Тараз", "kk": "Тараз", "en": "Taraz", "so": 1},
                    {"ru": "Шу", "kk": "Шу", "en": "Shu", "so": 2},
                    {"ru": "Каратау", "kk": "Қаратау", "en": "Karatau", "so": 3},
                    {"ru": "Жанатас", "kk": "Жаңатас", "en": "Zhanatas", "so": 4},
                    {"ru": "Мерке", "kk": "Мерке", "en": "Merke", "so": 5},
                ],
            },
            {
                "ru": "Акмолинская область",
                "kk": "Ақмола облысы",
                "en": "Akmola Region",
                "so": 7,
                "cities": [
                    {"ru": "Кокшетау", "kk": "Көкшетау", "en": "Kokshetau", "so": 1},
                    {"ru": "Степногорск", "kk": "Степногорск", "en": "Stepnogorsk", "so": 2},
                    {"ru": "Щучинск", "kk": "Щучинск", "en": "Shchuchinsk", "so": 3},
                    {"ru": "Акколь", "kk": "Ақкөл", "en": "Akkol", "so": 4},
                    {"ru": "Есиль", "kk": "Есіл", "en": "Esil", "so": 5},
                ],
            },
            {
                "ru": "Карагандинская область",
                "kk": "Қарағанды облысы",
                "en": "Karaganda Region",
                "so": 8,
                "cities": [
                    {"ru": "Караганда", "kk": "Қарағанды", "en": "Karaganda", "so": 1},
                    {"ru": "Темиртау", "kk": "Теміртау", "en": "Temirtau", "so": 2},
                    {"ru": "Абай", "kk": "Абай", "en": "Abay", "so": 3},
                    {"ru": "Шахтинск", "kk": "Шахтинск", "en": "Shakhtinsk", "so": 4},
                    {"ru": "Балхаш", "kk": "Балқаш", "en": "Balkhash", "so": 5},
                ],
            },
            {
                "ru": "Абайская область",
                "kk": "Абай облысы",
                "en": "Abai Region",
                "so": 9,
                "cities": [
                    {"ru": "Семей", "kk": "Семей", "en": "Semey", "so": 1},
                    {"ru": "Аягоз", "kk": "Аягөз", "en": "Ayagoz", "so": 2},
                    {"ru": "Жарма", "kk": "Жарма", "en": "Zharma", "so": 3},
                    {"ru": "Шар", "kk": "Шар", "en": "Shar", "so": 4},
                    {"ru": "Аягоз", "kk": "Аягөз", "en": "Ayagoz", "so": 5},
                ],
            },
            {
                "ru": "Павлодарская область",
                "kk": "Павлодар облысы",
                "en": "Pavlodar Region",
                "so": 10,
                "cities": [
                    {"ru": "Павлодар", "kk": "Павлодар", "en": "Pavlodar", "so": 1},
                    {"ru": "Экибастуз", "kk": "Екібастұз", "en": "Ekibastuz", "so": 2},
                    {"ru": "Аксу", "kk": "Ақсу", "en": "Aksu", "so": 3},
                    {"ru": "Ертис", "kk": "Ертіс", "en": "Ertis", "so": 4},
                    {"ru": "Шарбакты", "kk": "Шарбақты", "en": "Sharbakty", "so": 5},
                ],
            },
            {
                "ru": "Восточно-Казахстанская область",
                "kk": "Шығыс Қазақстан облысы",
                "en": "East Kazakhstan Region",
                "so": 11,
                "cities": [
                    {"ru": "Усть-Каменогорск", "kk": "Өскемен", "en": "Ust-Kamenogorsk", "so": 1},
                    {"ru": "Риддер", "kk": "Риддер", "en": "Ridder", "so": 2},
                    {"ru": "Алтай", "kk": "Алтай", "en": "Altai", "so": 3},
                    {"ru": "Серебрянск", "kk": "Серебрянск", "en": "Serebryansk", "so": 4},
                    {"ru": "Курчатов", "kk": "Курчатов", "en": "Kurchatov", "so": 5},
                ],
            },
            {
                "ru": "Северо-Казахстанская область",
                "kk": "Солтүстік Қазақстан облысы",
                "en": "North Kazakhstan Region",
                "so": 12,
                "cities": [
                    {"ru": "Петропавл", "kk": "Петропавл", "en": "Petropavl", "so": 1},
                    {"ru": "Тайынша", "kk": "Тайынша", "en": "Tayynsha", "so": 2},
                    {"ru": "Мамлют", "kk": "Мамлют", "en": "Mamlyut", "so": 3},
                    {"ru": "Есиль", "kk": "Есіл", "en": "Esil", "so": 4},
                    {"ru": "Сергеевка", "kk": "Сергеевка", "en": "Sergeyevka", "so": 5},
                ],
            },
            {
                "ru": "Костанайская область",
                "kk": "Қостанай облысы",
                "en": "Kostanay Region",
                "so": 13,
                "cities": [
                    {"ru": "Костанай", "kk": "Қостанай", "en": "Kostanay", "so": 1},
                    {"ru": "Рудный", "kk": "Рудный", "en": "Rudny", "so": 2},
                    {"ru": "Лисаковск", "kk": "Лисаковск", "en": "Lisakovsk", "so": 3},
                    {"ru": "Аркалык", "kk": "Арқалық", "en": "Arkalyk", "so": 4},
                    {"ru": "Житикара", "kk": "Жітіқара", "en": "Zhitikara", "so": 5},
                ],
            },
            {
                "ru": "Актюбинская область",
                "kk": "Ақтөбе облысы",
                "en": "Aktobe Region",
                "so": 14,
                "cities": [
                    {"ru": "Актобе", "kk": "Ақтөбе", "en": "Aktobe", "so": 1},
                    {"ru": "Хромтау", "kk": "Хромтау", "en": "Khromtau", "so": 2},
                    {"ru": "Шалкар", "kk": "Шалқар", "en": "Shalkar", "so": 3},
                    {"ru": "Темир", "kk": "Темір", "en": "Temir", "so": 4},
                    {"ru": "Алга", "kk": "Алға", "en": "Alga", "so": 5},
                ],
            },
            {
                "ru": "Западно-Казахстанская область",
                "kk": "Батыс Қазақстан облысы",
                "en": "West Kazakhstan Region",
                "so": 15,
                "cities": [
                    {"ru": "Орал", "kk": "Орал", "en": "Oral", "so": 1},
                    {"ru": "Аксай", "kk": "Ақсай", "en": "Aksai", "so": 2},
                    {"ru": "Жаңала", "kk": "Жаңала", "en": "Zhanala", "so": 3},
                    {"ru": "Шыңғырлау", "kk": "Шыңғырлау", "en": "Shyngyrlay", "so": 4},
                    {"ru": "Казталовка", "kk": "Қазталовка", "en": "Kaztalovka", "so": 5},
                ],
            },
            {
                "ru": "Атырауская область",
                "kk": "Атырау облысы",
                "en": "Atyrau Region",
                "so": 16,
                "cities": [
                    {"ru": "Атырау", "kk": "Атырау", "en": "Atyrau", "so": 1},
                    {"ru": "Кульсары", "kk": "Күлсары", "en": "Kulsary", "so": 2},
                    {"ru": "Доссор", "kk": "Доссор", "en": "Dossor", "so": 3},
                    {"ru": "Индер", "kk": "Індер", "en": "Inder", "so": 4},
                    {"ru": "Махамбет", "kk": "Махамбет", "en": "Makhambет", "so": 5},
                ],
            },
            {
                "ru": "Мангыстауская область",
                "kk": "Маңғыстау облысы",
                "en": "Mangystau Region",
                "so": 17,
                "cities": [
                    {"ru": "Актау", "kk": "Ақтау", "en": "Aktau", "so": 1},
                    {"ru": "Жанаозен", "kk": "Жаңаөзен", "en": "Zhanaozen", "so": 2},
                    {"ru": "Бейнеу", "kk": "Бейнеу", "en": "Beyney", "so": 3},
                    {"ru": "Форт-Шевченко", "kk": "Форт-Шевченко", "en": "Fort-Shevchenko", "so": 4},
                    {"ru": "Шетпе", "kk": "Шетпе", "en": "Shetpe", "so": 5},
                ],
            },
            {
                "ru": "Кызылординская область",
                "kk": "Қызылорда облысы",
                "en": "Kyzylorda Region",
                "so": 18,
                "cities": [
                    {"ru": "Кызылорда", "kk": "Қызылорда", "en": "Kyzylorda", "so": 1},
                    {"ru": "Байконур", "kk": "Байқоңыр", "en": "Baikonur", "so": 2},
                    {"ru": "Аральск", "kk": "Арал", "en": "Aralsk", "so": 3},
                    {"ru": "Жосалы", "kk": "Жосалы", "en": "Zhosaly", "so": 4},
                    {"ru": "Шиели", "kk": "Шиелі", "en": "Shieli", "so": 5},
                ],
            },
            {
                "ru": "Туркестанская область",
                "kk": "Түркістан облысы",
                "en": "Turkestan Region",
                "so": 19,
                "cities": [
                    {"ru": "Туркестан", "kk": "Түркістан", "en": "Turkestan", "so": 1},
                    {"ru": "Кентау", "kk": "Кентау", "en": "Kentau", "so": 2},
                    {"ru": "Сарыагаш", "kk": "Сарыағаш", "en": "Saryagash", "so": 3},
                    {"ru": "Арыс", "kk": "Арыс", "en": "Arys", "so": 4},
                    {"ru": "Ленгер", "kk": "Ленгер", "en": "Lenger", "so": 5},
                ],
            },
            {
                "ru": "Ұлытауская область",
                "kk": "Ұлытау облысы",
                "en": "Ulytau Region",
                "so": 20,
                "cities": [
                    {"ru": "Жезказган", "kk": "Жезқазған", "en": "Zhezkazgan", "so": 1},
                    {"ru": "Сатпаев", "kk": "Сатпаев", "en": "Satpaev", "so": 2},
                    {"ru": "Жайрем", "kk": "Жайрем", "en": "Zhairem", "so": 3},
                    {"ru": "Ұлытау", "kk": "Ұлытау", "en": "Ulytau", "so": 4},
                    {"ru": "Жезді", "kk": "Жезді", "en": "Zhezdi", "so": 5},
                ],
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Kyrgyzstan
    # -----------------------------------------------------------------------
    {
        "ru": "Кыргызстан",
        "kk": "Қырғызстан",
        "en": "Kyrgyzstan",
        "so": 2,
        "regions": [
            {
                "ru": "Иссык-Кульская область",
                "kk": "Ысык-Көл облусу",
                "en": "Issyk-Kul Region",
                "so": 1,
                "cities": [
                    {"ru": "Каракол", "kk": "Каракол", "en": "Karakol", "so": 1},
                    {"ru": "Балыкчы", "kk": "Балыкчы", "en": "Balykchy", "so": 2},
                    {"ru": "Чолпон-Ата", "kk": "Чолпон-Ата", "en": "Cholpon-Ata", "so": 3},
                    {"ru": "Тюп", "kk": "Тюп", "en": "Tyup", "so": 4},
                    {"ru": "Боконбаево", "kk": "Боконбаево", "en": "Bokonbayevo", "so": 5},
                ],
            },
            {
                "ru": "Бишкек",
                "kk": "Бишкек",
                "en": "Bishkek",
                "so": 2,
                "cities": [
                    {"ru": "Бишкек", "kk": "Бишкек", "en": "Bishkek", "so": 1},
                ],
            },
            {
                "ru": "Чуйская область",
                "kk": "Чүй облусу",
                "en": "Chuy Region",
                "so": 3,
                "cities": [
                    {"ru": "Токмок", "kk": "Токмок", "en": "Tokmok", "so": 1},
                    {"ru": "Кара-Балта", "kk": "Кара-Балта", "en": "Kara-Balta", "so": 2},
                    {"ru": "Кант", "kk": "Кант", "en": "Kant", "so": 3},
                    {"ru": "Беловодское", "kk": "Беловодское", "en": "Belovodskoe", "so": 4},
                    {"ru": "Шопоков", "kk": "Шопоков", "en": "Shopokov", "so": 5},
                ],
            },
            {
                "ru": "Ошская область",
                "kk": "Ош облусу",
                "en": "Osh Region",
                "so": 4,
                "cities": [
                    {"ru": "Узген", "kk": "Өзгөн", "en": "Uzgen", "so": 1},
                    {"ru": "Ноокат", "kk": "Ноокат", "en": "Nookat", "so": 2},
                    {"ru": "Кара-Суу", "kk": "Кара-Суу", "en": "Kara-Suu", "so": 3},
                    {"ru": "Гулча", "kk": "Гүлчө", "en": "Gulcha", "so": 4},
                    {"ru": "Кара-Кулджа", "kk": "Кара-Кулджа", "en": "Kara-Kulja", "so": 5},
                ],
            },
            {
                "ru": "Ош",
                "kk": "Ош",
                "en": "Osh",
                "so": 5,
                "cities": [
                    {"ru": "Ош", "kk": "Ош", "en": "Osh", "so": 1},
                ],
            },
            {
                "ru": "Джалал-Абадская область",
                "kk": "Жалал-Абад облусу",
                "en": "Jalal-Abad Region",
                "so": 6,
                "cities": [
                    {"ru": "Жалал-Абад", "kk": "Жалал-Абад", "en": "Jalal-Abad", "so": 1},
                    {"ru": "Ташкумыр", "kk": "Таш-Көмүр", "en": "Tash-Kumyr", "so": 2},
                    {"ru": "Кочкор-Ата", "kk": "Кочкор-Ата", "en": "Kochkor-Ata", "so": 3},
                    {"ru": "Майлуу-Суу", "kk": "Майлуу-Суу", "en": "Mayluu-Suu", "so": 4},
                    {"ru": "Токтогул", "kk": "Токтогул", "en": "Toktogul", "so": 5},
                ],
            },
            {
                "ru": "Нарынская область",
                "kk": "Нарын облусу",
                "en": "Naryn Region",
                "so": 7,
                "cities": [
                    {"ru": "Нарын", "kk": "Нарын", "en": "Naryn", "so": 1},
                    {"ru": "Ат-Башы", "kk": "Ат-Башы", "en": "At-Bashy", "so": 2},
                    {"ru": "Кочкор", "kk": "Кочкор", "en": "Kochkor", "so": 3},
                    {"ru": "Жумгал", "kk": "Жумгал", "en": "Zhumgal", "so": 4},
                    {"ru": "Чаек", "kk": "Чаек", "en": "Chayek", "so": 5},
                ],
            },
            {
                "ru": "Баткенская область",
                "kk": "Баткен облусу",
                "en": "Batken Region",
                "so": 8,
                "cities": [
                    {"ru": "Баткен", "kk": "Баткен", "en": "Batken", "so": 1},
                    {"ru": "Кызыл-Кия", "kk": "Кызыл-Кыя", "en": "Kyzyl-Kiya", "so": 2},
                    {"ru": "Исфана", "kk": "Исфана", "en": "Isfana", "so": 3},
                    {"ru": "Сулюкта", "kk": "Сүлүктү", "en": "Sulukta", "so": 4},
                    {"ru": "Кадамжай", "kk": "Кадамжай", "en": "Kadamzhay", "so": 5},
                ],
            },
            {
                "ru": "Таласская область",
                "kk": "Талас облусу",
                "en": "Talas Region",
                "so": 9,
                "cities": [
                    {"ru": "Талас", "kk": "Талас", "en": "Talas", "so": 1},
                    {"ru": "Манас", "kk": "Манас", "en": "Manas", "so": 2},
                    {"ru": "Кара-Буура", "kk": "Кара-Буура", "en": "Kara-Buura", "so": 3},
                    {"ru": "Бакай-Ата", "kk": "Бакай-Ата", "en": "Bakay-Ata", "so": 4},
                    {"ru": "Кызыл-Адыр", "kk": "Кызыл-Адыр", "en": "Kyzyl-Adir", "so": 5},
                ],
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Russia
    # -----------------------------------------------------------------------
    {
        "ru": "Россия",
        "kk": "Ресей",
        "en": "Russia",
        "so": 3,
        "regions": [
            {
                "ru": "Москва",
                "kk": "Мәскеу",
                "en": "Moscow",
                "so": 1,
                "cities": [
                    {"ru": "Москва", "kk": "Мәскеу", "en": "Moscow", "so": 1},
                ],
            },
            {
                "ru": "Санкт-Петербург",
                "kk": "Санкт-Петербург",
                "en": "Saint Petersburg",
                "so": 2,
                "cities": [
                    {"ru": "Санкт-Петербург", "kk": "Санкт-Петербург", "en": "Saint Petersburg", "so": 1},
                ],
            },
            {
                "ru": "Краснодарский край",
                "kk": "Краснодар өлкесі",
                "en": "Krasnodar Krai",
                "so": 3,
                "cities": [
                    {"ru": "Краснодар", "kk": "Краснодар", "en": "Krasnodar", "so": 1},
                    {"ru": "Сочи", "kk": "Сочи", "en": "Sochi", "so": 2},
                    {"ru": "Новороссийск", "kk": "Новороссийск", "en": "Novorossiysk", "so": 3},
                    {"ru": "Геленджик", "kk": "Геленджик", "en": "Gelendzhik", "so": 4},
                    {"ru": "Анапа", "kk": "Анапа", "en": "Anapa", "so": 5},
                ],
            },
            {
                "ru": "Свердловская область",
                "kk": "Свердлов облысы",
                "en": "Sverdlovsk Region",
                "so": 4,
                "cities": [
                    {"ru": "Екатеринбург", "kk": "Екатеринбург", "en": "Yekaterinburg", "so": 1},
                    {"ru": "Нижний Тагил", "kk": "Нижний Тагил", "en": "Nizhny Tagil", "so": 2},
                    {"ru": "Каменск-Уральский", "kk": "Каменск-Уральский", "en": "Kamensk-Uralsky", "so": 3},
                    {"ru": "Первоуральск", "kk": "Первоуральск", "en": "Pervouralsk", "so": 4},
                    {"ru": "Серов", "kk": "Серов", "en": "Serov", "so": 5},
                ],
            },
            {
                "ru": "Алтайский край",
                "kk": "Алтай өлкесі",
                "en": "Altai Krai",
                "so": 5,
                "cities": [
                    {"ru": "Барнаул", "kk": "Барнаул", "en": "Barnaul", "so": 1},
                    {"ru": "Бийск", "kk": "Бийск", "en": "Biysk", "so": 2},
                    {"ru": "Рубцовск", "kk": "Рубцовск", "en": "Rubtsovsk", "so": 3},
                    {"ru": "Новоалтайск", "kk": "Новоалтайск", "en": "Novoaltaysk", "so": 4},
                    {"ru": "Заринск", "kk": "Заринск", "en": "Zarinsk", "so": 5},
                ],
            },
            {
                "ru": "Новосибирская область",
                "kk": "Новосибирск облысы",
                "en": "Novosibirsk Region",
                "so": 6,
                "cities": [
                    {"ru": "Новосибирск", "kk": "Новосибирск", "en": "Novosibirsk", "so": 1},
                    {"ru": "Бердск", "kk": "Бердск", "en": "Berdsk", "so": 2},
                    {"ru": "Искитим", "kk": "Искитим", "en": "Iskitim", "so": 3},
                    {"ru": "Обь", "kk": "Обь", "en": "Ob", "so": 4},
                    {"ru": "Куйбышев", "kk": "Куйбышев", "en": "Kuybyshev", "so": 5},
                ],
            },
            {
                "ru": "Омская область",
                "kk": "Омск облысы",
                "en": "Omsk Region",
                "so": 7,
                "cities": [
                    {"ru": "Омск", "kk": "Омск", "en": "Omsk", "so": 1},
                    {"ru": "Тара", "kk": "Тара", "en": "Tara", "so": 2},
                    {"ru": "Калачинск", "kk": "Калачинск", "en": "Kalachinsk", "so": 3},
                    {"ru": "Исилькуль", "kk": "Ісілкөл", "en": "Isilkul", "so": 4},
                    {"ru": "Называевск", "kk": "Называевск", "en": "Nazyvayevsk", "so": 5},
                ],
            },
            {
                "ru": "Красноярский край",
                "kk": "Красноярск өлкесі",
                "en": "Krasnoyarsk Krai",
                "so": 8,
                "cities": [
                    {"ru": "Красноярск", "kk": "Красноярск", "en": "Krasnoyarsk", "so": 1},
                    {"ru": "Норильск", "kk": "Норильск", "en": "Norilsk", "so": 2},
                    {"ru": "Ачинск", "kk": "Ачинск", "en": "Achinsk", "so": 3},
                    {"ru": "Канск", "kk": "Канск", "en": "Kansk", "so": 4},
                    {"ru": "Железногорск", "kk": "Железногорск", "en": "Zheleznogorsk", "so": 5},
                ],
            },
            {
                "ru": "Иркутская область",
                "kk": "Иркутск облысы",
                "en": "Irkutsk Region",
                "so": 9,
                "cities": [
                    {"ru": "Иркутск", "kk": "Иркутск", "en": "Irkutsk", "so": 1},
                    {"ru": "Ангарск", "kk": "Ангарск", "en": "Angarsk", "so": 2},
                    {"ru": "Братск", "kk": "Братск", "en": "Bratsk", "so": 3},
                    {"ru": "Усть-Илимск", "kk": "Усть-Илимск", "en": "Ust-Ilimsk", "so": 4},
                    {"ru": "Шелехов", "kk": "Шелехов", "en": "Shelekhov", "so": 5},
                ],
            },
            {
                "ru": "Республика Алтай",
                "kk": "Алтай Республикасы",
                "en": "Republic of Altai",
                "so": 10,
                "cities": [
                    {"ru": "Горно-Алтайск", "kk": "Горно-Алтайск", "en": "Gorno-Altaysk", "so": 1},
                    {"ru": "Майма", "kk": "Майма", "en": "Mayma", "so": 2},
                    {"ru": "Кош-Агач", "kk": "Кош-Ағаш", "en": "Kosh-Agach", "so": 3},
                    {"ru": "Онгудай", "kk": "Оңғудай", "en": "Ongudai", "so": 4},
                    {"ru": "Чемал", "kk": "Чемал", "en": "Chemal", "so": 5},
                ],
            },
        ],
    },
    # -----------------------------------------------------------------------
    # China
    # -----------------------------------------------------------------------
    {
        "ru": "Китай",
        "kk": "Қытай",
        "en": "China",
        "so": 4,
        "regions": [
            {
                "ru": "Синьцзян",
                "kk": "Шыңжаң",
                "en": "Xinjiang",
                "so": 1,
                "cities": [
                    {"ru": "Урумчи", "kk": "Үрімжі", "en": "Urumqi", "so": 1},
                    {"ru": "Инин", "kk": "Іле", "en": "Yining", "so": 2},
                    {"ru": "Кашгар", "kk": "Қашғар", "en": "Kashgar", "so": 3},
                    {"ru": "Хами", "kk": "Қомыл", "en": "Hami", "so": 4},
                    {"ru": "Корла", "kk": "Қорла", "en": "Korla", "so": 5},
                ],
            },
            {
                "ru": "Пекин",
                "kk": "Пекин",
                "en": "Beijing",
                "so": 2,
                "cities": [
                    {"ru": "Пекин", "kk": "Пекин", "en": "Beijing", "so": 1},
                ],
            },
            {
                "ru": "Шанхай",
                "kk": "Шанхай",
                "en": "Shanghai",
                "so": 3,
                "cities": [
                    {"ru": "Шанхай", "kk": "Шанхай", "en": "Shanghai", "so": 1},
                ],
            },
            {
                "ru": "Юньнань",
                "kk": "Юньнань",
                "en": "Yunnan",
                "so": 4,
                "cities": [
                    {"ru": "Куньмин", "kk": "Күнмин", "en": "Kunming", "so": 1},
                    {"ru": "Дали", "kk": "Дали", "en": "Dali", "so": 2},
                    {"ru": "Лицзян", "kk": "Лицзян", "en": "Lijiang", "so": 3},
                    {"ru": "Шангри-Ла", "kk": "Шангри-Ла", "en": "Shangri-La", "so": 4},
                    {"ru": "Пуэр", "kk": "Пуэр", "en": "Pu'er", "so": 5},
                ],
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Other country (catch-all — no predefined regions)
    # -----------------------------------------------------------------------
    {
        "ru": "Другая страна",
        "kk": "Басқа ел",
        "en": "Other country",
        "so": 9999,
        "regions": [],
    },
]


# ---------------------------------------------------------------------------
# Migration function
# ---------------------------------------------------------------------------


def populate_locations(apps, schema_editor):
    from locations.models import Location  # use real model for treebeard methods

    o_region = _OTHER["region"]
    o_city = _OTHER["city"]
    o_venue = _OTHER["venue"]

    def add_venue(parent, **extra):
        parent.add_child(
            name=o_venue["ru"],
            name_ru=o_venue["ru"],
            name_kk=o_venue["kk"],
            name_en=o_venue["en"],
            sort_order=9999,
            is_hidden=True,
            **extra,
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

    def add_other_region(parent):
        reg_node = parent.add_child(
            name=o_region["ru"],
            name_ru=o_region["ru"],
            name_kk=o_region["kk"],
            name_en=o_region["en"],
            sort_order=9999,
        )
        add_other_city(reg_node)

    for country_data in LOCATION_DATA:
        country = Location.add_root(
            name=country_data["ru"],
            name_ru=country_data["ru"],
            name_kk=country_data["kk"],
            name_en=country_data["en"],
            sort_order=country_data["so"],
        )

        for region_data in country_data["regions"]:
            region = country.add_child(
                name=region_data["ru"],
                name_ru=region_data["ru"],
                name_kk=region_data["kk"],
                name_en=region_data["en"],
                sort_order=region_data["so"],
            )

            for city_data in region_data["cities"]:
                city = region.add_child(
                    name=city_data["ru"],
                    name_ru=city_data["ru"],
                    name_kk=city_data["kk"],
                    name_en=city_data["en"],
                    sort_order=city_data["so"],
                )
                add_venue(city)

            add_other_city(region)

        add_other_region(country)


def remove_locations(apps, schema_editor):
    from locations.models import Location

    Location.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0003_location_sort_order"),
        ("wagtailsearch", "0010_add_text_fields"),
    ]

    operations = [
        migrations.RunPython(populate_locations, remove_locations),
    ]
