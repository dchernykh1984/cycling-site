from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0002_add_is_hidden_is_deleted"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="sort_order",
            field=models.PositiveSmallIntegerField(db_index=True, default=0),
        ),
    ]
