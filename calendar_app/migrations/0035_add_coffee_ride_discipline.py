from django.db import migrations

# A coffee ride -- a social road ride with a stop at a cafe -- is a format of its own, and a popular
# one: the calendar's coffee rides used to land in "Other (Road Cycling)". One discipline in the road
# direction, just before its catch-all, in all three locales.
_CATEGORY_EN = "Road Cycling"
_CATCH_ALL_EN = "Other (Road Cycling)"
_NAME_RU, _NAME_EN, _NAME_KK = "Кофе-райд", "Coffee Ride", "Кофе-райд"


def add_coffee_ride(apps, schema_editor):
    Discipline = apps.get_model("calendar_app", "Discipline")
    road = apps.get_model("calendar_app", "DisciplineCategory").objects.filter(name_en=_CATEGORY_EN).first()
    if road is None or Discipline.objects.filter(category=road, name_en=_NAME_EN).exists():
        return
    catch_all = Discipline.objects.filter(category=road, name_en=_CATCH_ALL_EN).first()
    if catch_all is not None:
        order = catch_all.order
        catch_all.order += 1
        catch_all.save(update_fields=["order"])
    else:
        last = Discipline.objects.filter(category=road).order_by("-order").first()
        order = (last.order + 1) if last else 1
    Discipline.objects.create(
        category=road, name=_NAME_RU, name_ru=_NAME_RU, name_en=_NAME_EN, name_kk=_NAME_KK, order=order
    )


def remove_coffee_ride(apps, schema_editor):
    """Reverse: drop the discipline and put the catch-all back -- but refuse if any competition uses
    it, so a rollback never silently strips a competition of its discipline."""
    Discipline = apps.get_model("calendar_app", "Discipline")
    ride = Discipline.objects.filter(category__name_en=_CATEGORY_EN, name_en=_NAME_EN).first()
    if ride is None:
        return
    if ride.competitions.exists():
        raise RuntimeError("Cannot reverse 0035: the coffee ride discipline is linked to competitions.")
    Discipline.objects.filter(category=ride.category, name_en=_CATCH_ALL_EN, order=ride.order + 1).update(
        order=ride.order
    )
    ride.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calendar_app", "0034_competition_preview_text"),
    ]

    operations = [
        migrations.RunPython(add_coffee_ride, remove_coffee_ride),
    ]
