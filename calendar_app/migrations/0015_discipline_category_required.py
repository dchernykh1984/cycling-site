import django.db.models.deletion
from django.db import migrations, models


def assign_orphan_disciplines(apps, schema_editor):
    """Every discipline must belong to a direction; park any legacy NULL-category disciplines under
    a fallback category so the column can be made non-nullable. No-op when there are none."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    DisciplineCategory = apps.get_model("calendar_app", "DisciplineCategory")
    orphans = Discipline.objects.filter(category__isnull=True)
    if not orphans.exists():
        return
    fallback, _ = DisciplineCategory.objects.get_or_create(name="Uncategorized", defaults={"order": 9999})
    orphans.update(category=fallback)


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0014_competition_disciplines"),
    ]

    operations = [
        migrations.RunPython(assign_orphan_disciplines, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="discipline",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="disciplines",
                to="calendar_app.disciplinecategory",
            ),
        ),
    ]
