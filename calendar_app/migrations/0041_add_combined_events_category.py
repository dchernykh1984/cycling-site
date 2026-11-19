from django.db import migrations

# All-round competitions -- several exercises scored into one result, such as a general physical
# preparation meet of a 60 m sprint, pull-ups and a standing long jump -- had no direction to land
# in: the nearest, the triathlon family, race their legs back to back for one time rather than
# score exercises. One new direction with the established kinds, general physical preparation
# first, in all three locales and in the shape every direction has: (order, name_ru, name_en,
# name_kk), the catch-all last.
_CATEGORY_RU, _CATEGORY_EN, _CATEGORY_KK = "Многоборье", "Combined Events", "Көпсайыс"
_DISCIPLINES = [
    (1, "Общая физическая подготовка", "General Physical Preparation", "Жалпы дене дайындығы"),
    (2, "Лёгкоатлетическое многоборье", "Athletics Combined Events", "Жеңіл атлетикалық көпсайыс"),
    (3, "Полиатлон", "Polyathlon", "Полиатлон"),
    (4, "Современное пятиборье", "Modern Pentathlon", "Қазіргі бессайыс"),
    (5, "Другое (Многоборье)", "Other (Combined Events)", "Басқа (Көпсайыс)"),
]
_NAMES_EN = [name_en for _, _, name_en, _ in _DISCIPLINES]


def add_combined_events(apps, schema_editor):
    DisciplineCategory = apps.get_model("calendar_app", "DisciplineCategory")
    Discipline = apps.get_model("calendar_app", "Discipline")
    last = DisciplineCategory.objects.order_by("-order").first()
    category, _ = DisciplineCategory.objects.get_or_create(
        name_en=_CATEGORY_EN,
        defaults={
            "name": _CATEGORY_RU,
            "name_ru": _CATEGORY_RU,
            "name_kk": _CATEGORY_KK,
            "order": (last.order + 1) if last else 1,
        },
    )
    for order, name_ru, name_en, name_kk in _DISCIPLINES:
        Discipline.objects.get_or_create(
            name_en=name_en,
            category=category,
            defaults={"name": name_ru, "name_ru": name_ru, "name_kk": name_kk, "order": order},
        )


def remove_combined_events(apps, schema_editor):
    """Reverse: drop the direction and its disciplines -- but refuse if any competition uses them,
    so a rollback never silently strips a competition of its discipline."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    DisciplineCategory = apps.get_model("calendar_app", "DisciplineCategory")
    qs = Discipline.objects.filter(category__name_en=_CATEGORY_EN, name_en__in=_NAMES_EN)
    linked = sorted(qs.filter(competitions__isnull=False).values_list("pk", flat=True).distinct())
    if linked:
        raise RuntimeError(f"Cannot reverse 0041: combined-events disciplines {linked} are linked to competitions.")
    qs.delete()
    DisciplineCategory.objects.filter(name_en=_CATEGORY_EN, disciplines__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0040_additional_info_birth_date"),
    ]

    operations = [
        migrations.RunPython(add_combined_events, remove_combined_events),
    ]
