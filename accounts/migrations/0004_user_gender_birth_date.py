from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_theme"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("M", "Male"), ("F", "Female")],
                default="",
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="birth_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
