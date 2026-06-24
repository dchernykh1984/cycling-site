from django.db import migrations

# The generic discipline (English name "Other") exists once per direction, so on the site several
# of them collapse to a bare, ambiguous label. Match those rows by the ASCII English name so the
# rename step needs no non-ASCII literals (the direction suffix itself is read from the DB).
_GENERIC_NAME_EN = "Other"

# New Mountain Bike disciplines: (order, name_ru, name_en, name_kk).
_NEW_MTB_DISCIPLINES = [
    (
        13,
        "Индивидуальная гонка с раздельного старта (МТБ)",
        "Individual Time Trial (MTB)",
        "Жеке уақыт сынақ жарысы (МТБ)",
    ),
    (14, "Гонка в гору (МТБ)", "Hill Climb (MTB)", "Тауға өрлеу жарысы (МТБ)"),
]
_NEW_MTB_NAMES_EN = [name_en for _, _, name_en, _ in _NEW_MTB_DISCIPLINES]


def qualify_other_disciplines(apps, schema_editor):
    """Append the direction to each generic discipline in every locale, e.g.
    "Other" -> "Other (Mountain Bike)", so the per-direction copies are distinguishable."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    for d in Discipline.objects.filter(name_en=_GENERIC_NAME_EN).select_related("category"):
        cat = d.category
        for loc in ("ru", "kk", "en"):
            base = getattr(d, f"name_{loc}")
            cat_name = getattr(cat, f"name_{loc}") or cat.name_ru
            if base and cat_name:
                setattr(d, f"name_{loc}", f"{base} ({cat_name})")
        d.name = d.name_ru or d.name
        d.save(update_fields=["name", "name_ru", "name_kk", "name_en"])


def strip_direction_suffix(apps, schema_editor):
    """Reverse: restore the bare generic name, but only on the rows this migration itself renamed
    (English name is exactly "Other (<own category>)"), so disciplines created or edited afterwards
    are left untouched."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    for d in Discipline.objects.select_related("category").filter(name_en__startswith=f"{_GENERIC_NAME_EN} ("):
        cat = d.category
        if d.name_en != f"{_GENERIC_NAME_EN} ({cat.name_en})":
            continue  # not produced by this migration's forward step
        for loc in ("ru", "kk", "en"):
            base = getattr(d, f"name_{loc}")
            suffix = f" ({getattr(cat, f'name_{loc}') or cat.name_ru})"
            if base and base.endswith(suffix):
                setattr(d, f"name_{loc}", base[: -len(suffix)])
        ru_suffix = f" ({cat.name_ru})"
        if d.name and d.name.endswith(ru_suffix):
            d.name = d.name[: -len(ru_suffix)]
        d.save(update_fields=["name", "name_ru", "name_kk", "name_en"])


def add_mtb_disciplines(apps, schema_editor):
    """Add the two missing Mountain Bike race formats (ITT and Hill Climb) in all three locales."""
    DisciplineCategory = apps.get_model("calendar_app", "DisciplineCategory")
    Discipline = apps.get_model("calendar_app", "Discipline")
    mtb = DisciplineCategory.objects.filter(name_en="Mountain Bike").first()
    if mtb is None:
        return
    for order, name_ru, name_en, name_kk in _NEW_MTB_DISCIPLINES:
        Discipline.objects.get_or_create(
            name_ru=name_ru,
            category=mtb,
            defaults={"name": name_ru, "name_en": name_en, "name_kk": name_kk, "order": order},
        )


def remove_mtb_disciplines(apps, schema_editor):
    """Reverse: delete the two Mountain Bike formats added above -- but refuse the rollback if any of
    them is already linked to a competition, so it never silently drops a competition's discipline."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    qs = Discipline.objects.filter(category__name_en="Mountain Bike", name_en__in=_NEW_MTB_NAMES_EN)
    linked = sorted(qs.filter(competitions__isnull=False).values_list("pk", flat=True).distinct())
    if linked:
        raise RuntimeError(f"Cannot reverse 0016: Mountain Bike disciplines {linked} are linked to competitions.")
    qs.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0015_discipline_category_required"),
    ]

    operations = [
        migrations.RunPython(qualify_other_disciplines, strip_direction_suffix),
        migrations.RunPython(add_mtb_disciplines, remove_mtb_disciplines),
    ]
