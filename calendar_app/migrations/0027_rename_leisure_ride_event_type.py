from django.db import migrations

# The event type hikes and walks land in was named when the calendar was cycling-only: ru
# "Тренировка / Прогулка" and kk "Жаттығу / Серуен" say nothing about a bicycle, but the English
# name says "Ride". With mountain outings now proposed by the Telegram agent, an English visitor
# would read a summit walk as a bike ride. Only the English name is wrong, so only it is renamed.
_OLD_EN = "Training / Leisure Ride"
_NEW_EN = "Training / Leisure Outing"


def _rename(apps, from_name: str, to_name: str) -> None:
    EventType = apps.get_model("calendar_app", "EventType")
    for event_type in EventType.objects.filter(name_en=from_name):
        event_type.name_en = to_name
        # ``name`` carries the Russian text (it is the untranslated base field), so it is left
        # alone -- touching it here would overwrite the ru label with an English one.
        event_type.save(update_fields=["name_en"])


def rename_forward(apps, schema_editor):
    _rename(apps, _OLD_EN, _NEW_EN)


def rename_back(apps, schema_editor):
    _rename(apps, _NEW_EN, _OLD_EN)


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0026_add_hiking_category"),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_back),
    ]
