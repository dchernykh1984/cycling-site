"""Kazakh names for the countries and regions that carried their Russian one, and Latin English names.

``0015_all_countries`` seeded every country with its Russian name in the Kazakh column, and regions
added since came the same way: a Kazakh reader saw "Монголия" and "Ставропольский край" where Kazakh
writes "Моңғолия" and "Ставрополь өлкесі". Most countries are written alike in both languages
("Германия", "Франция") and keep their name; the ones below differ.

Only a Kazakh name that is empty or still the Russian one is replaced -- a name a person wrote is
left exactly as it is -- and a region is found under its own country, since names repeat across
countries. An English name written in Cyrillic, which no English reader can use, becomes the Russian
name in Latin letters.
"""

from django.db import migrations

COUNTRIES = {
    "Монголия": "Моңғолия",
    "Таджикистан": "Тәжікстан",
    "Туркмения": "Түрікменстан",
    "Азербайджан": "Әзірбайжан",
    "Афганистан": "Ауғанстан",
    "Индия": "Үндістан",
    "Япония": "Жапония",
    "Греция": "Грекия",
    "Саудовская Аравия": "Сауд Арабиясы",
    "ОАЭ": "БАӘ",
    "Республика Корея": "Корея Республикасы",
    "КНДР": "КХДР",
    "Новая Зеландия": "Жаңа Зеландия",
    "Нидерланды": "Нидерланд",
    "Филиппины": "Филиппин",
    "Южный Судан": "Оңтүстік Судан",
    "Восточный Тимор": "Шығыс Тимор",
    "Молдавия": "Молдова",
    "Таиланд": "Тайланд",
    "Босния и Герцеговина": "Босния және Герцеговина",
    "Антигуа и Барбуда": "Антигуа және Барбуда",
    "Сан-Томе и Принсипи": "Сан-Томе және Принсипи",
    "Сент-Винсент и Гренадины": "Сент-Винсент және Гренадиндер",
    "Сент-Китс и Невис": "Сент-Китс және Невис",
    "Тринидад и Тобаго": "Тринидад және Тобаго",
    "Доминиканская Республика": "Доминикан Республикасы",
    "Экваториальная Гвинея": "Экваторлық Гвинея",
    "Республика Конго": "Конго Республикасы",
    "ДР Конго": "Конго Демократиялық Республикасы",
    "ЦАР": "Орталық Африка Республикасы",
    "Маршалловы Острова": "Маршалл аралдары",
    "Соломоновы Острова": "Соломон аралдары",
    "Папуа — Новая Гвинея": "Папуа — Жаңа Гвинея",
    "Мальдивы": "Мальдив",
    "Сейшелы": "Сейшел аралдары",
    "Коморы": "Комор аралдары",
    "Багамы": "Багам аралдары",
}

# (country, region) -> the region's Kazakh name.
REGIONS = {
    ("Россия", "Самарская область"): "Самара облысы",
    ("Россия", "Нижегородская область"): "Нижний Новгород облысы",
    ("Россия", "Амурская область"): "Амур облысы",
    ("Россия", "Ставропольский край"): "Ставрополь өлкесі",
    ("Россия", "Приморский край"): "Приморье өлкесі",
    ("Россия", "Забайкальский край"): "Забайкал өлкесі",
    ("Россия", "Камчатский край"): "Камчатка өлкесі",
    ("Чехия", "Либерецкий край"): "Либерец өлкесі",
    ("Словакия", "Кошицкий край"): "Кошице өлкесі",
    ("Словакия", "Братиславский край"): "Братислава өлкесі",
    ("ЮАР", "Западно-Капская провинция"): "Батыс Кейп провинциясы",
    ("США", "Округ Колумбия"): "Колумбия округі",
    ("Бразилия", "Федеральный округ"): "Федералдық округ",
    ("Австралия", "Австралийская столичная территория"): "Аустралия астаналық аумағы",
    ("Бельгия", "Брюссельский столичный регион"): "Брюссель астаналық аймағы",
    ("Буркина-Фасо", "Центральная область"): "Орталық аймақ",
    ("Сьерра-Леоне", "Западная область"): "Батыс аймақ",
    ("Того", "Приморская область"): "Теңіз жағалауы аймағы",
    ("Венесуэла", "Столичный округ"): "Астаналық округ",
    ("Доминиканская Республика", "Национальный округ"): "Ұлттық округ",
    ("Колумбия", "Столичный округ Богота"): "Богота астаналық округі",
    ("Папуа — Новая Гвинея", "Национальный столичный округ"): "Ұлттық астаналық округ",
    ("Фиджи", "Центральный округ"): "Орталық округ",
}

LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ә": "a",
    "ғ": "g",
    "қ": "q",
    "ң": "ng",
    "ө": "o",
    "ұ": "u",
    "ү": "u",
    "һ": "h",
    "і": "i",
}


def in_latin(text: str) -> str:
    out = []
    for letter in text:
        latin = LATIN.get(letter.lower())
        if latin is None:
            out.append(letter)
        else:
            out.append(latin.capitalize() if letter.isupper() else latin)
    return "".join(out)


def _untouched(node) -> bool:
    return (node.name_kk or "") in ("", node.name_ru or "")


def name_them(apps, schema_editor):
    Location = apps.get_model("locations", "Location")
    named = 0
    for node in Location.objects.filter(depth=1, name_ru__in=list(COUNTRIES)):
        if _untouched(node):
            node.name_kk = COUNTRIES[node.name_ru]
            node.save(update_fields=["name_kk"])
            named += 1
    for (country_name, region_name), kazakh in REGIONS.items():
        for country in Location.objects.filter(depth=1, name_ru=country_name):
            under = Location.objects.filter(depth=2, name_ru=region_name, path__startswith=country.path)
            for node in under:
                if _untouched(node):
                    node.name_kk = kazakh
                    node.save(update_fields=["name_kk"])
                    named += 1
    latin = 0
    for node in Location.objects.filter(name_en__regex=r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]"):
        node.name_en = in_latin(node.name_ru or node.name_en)
        node.save(update_fields=["name_en"])
        latin += 1
    if named or latin:
        print(f"  named {named} place(s) in Kazakh, {latin} in Latin letters for English")


def keep(apps, schema_editor):
    """Deliberately not reversible in data: nothing here is worth putting back wrong."""


class Migration(migrations.Migration):
    dependencies = [("locations", "0017_repair_catch_all_venue_names")]

    operations = [migrations.RunPython(name_them, keep)]
