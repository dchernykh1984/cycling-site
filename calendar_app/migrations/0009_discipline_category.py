import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0008_add_is_hidden_is_deleted"),
    ]

    operations = [
        # Add order to EventType and change ordering
        migrations.AddField(
            model_name="eventtype",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="eventtype",
            options={
                "ordering": ["order"],
                "verbose_name": "Event type",
                "verbose_name_plural": "Event types",
            },
        ),
        # Rename CyclingDiscipline -> Discipline
        migrations.RenameModel(
            old_name="CyclingDiscipline",
            new_name="Discipline",
        ),
        # Add order to Discipline
        migrations.AddField(
            model_name="discipline",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        # Create DisciplineCategory with translated name fields
        migrations.CreateModel(
            name="DisciplineCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("name_ru", models.CharField(max_length=100, null=True)),
                ("name_kk", models.CharField(max_length=100, null=True)),
                ("name_en", models.CharField(max_length=100, null=True)),
                ("order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Discipline category",
                "verbose_name_plural": "Discipline categories",
                "ordering": ["order"],
            },
        ),
        # Add category FK to Discipline (nullable: existing rows have no category yet)
        migrations.AddField(
            model_name="discipline",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="disciplines",
                to="calendar_app.disciplinecategory",
            ),
        ),
        # Update Discipline ordering and verbose names
        migrations.AlterModelOptions(
            name="discipline",
            options={
                "ordering": ["category__order", "order"],
                "verbose_name": "Discipline",
                "verbose_name_plural": "Disciplines",
            },
        ),
    ]
