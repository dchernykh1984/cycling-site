from django.db import migrations

# The mountain-community channels the Telegram agent reads announce walks, hikes and ascents, and
# until now those had no discipline to land in: the taxonomy carried six cycling directions, ski
# racing, running and the triathlons, but nothing on foot. One new category, in all three locales,
# following the shape every other category has: (order, name_ru, name_en, name_kk).
_CATEGORY_RU, _CATEGORY_EN, _CATEGORY_KK = "Пеший туризм", "Hiking", "Жаяу туризм"
_DISCIPLINES = [
    (1, "Однодневный поход", "Day Hike", "Бір күндік жорық"),
    (2, "Многодневный поход", "Multi-Day Trek", "Көп күндік жорық"),
    (3, "Восхождение", "Summit Hike", "Шыңға көтерілу"),
    (4, "Другое (Пеший туризм)", "Other (Hiking)", "Басқа (Жаяу туризм)"),
]
_NAMES_EN = [name_en for _, _, name_en, _ in _DISCIPLINES]


def add_hiking(apps, schema_editor):
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
            name_ru=name_ru,
            category=category,
            defaults={"name": name_ru, "name_en": name_en, "name_kk": name_kk, "order": order},
        )


def remove_hiking(apps, schema_editor):
    """Reverse: drop the category and its disciplines -- but refuse if any competition uses them,
    so a rollback never silently strips a competition of its discipline."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    DisciplineCategory = apps.get_model("calendar_app", "DisciplineCategory")
    qs = Discipline.objects.filter(category__name_en=_CATEGORY_EN, name_en__in=_NAMES_EN)
    linked = sorted(qs.filter(competitions__isnull=False).values_list("pk", flat=True).distinct())
    if linked:
        raise RuntimeError(f"Cannot reverse 0026: hiking disciplines {linked} are linked to competitions.")
    qs.delete()
    DisciplineCategory.objects.filter(name_en=_CATEGORY_EN, disciplines__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0025_competitionreport"),
    ]

    operations = [
        migrations.RunPython(add_hiking, remove_hiking),
    ]
