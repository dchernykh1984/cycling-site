"""Give the cities' catch-all venues their real names back.

``get_or_create_other_location`` translated "Other location" through a variable, which xgettext
cannot follow, so the string never reached the catalogues and gettext handed back the English source
for every language. Every catch-all created at runtime since then was born called "Other location"
in Russian and Kazakh alike, while the 1296 seeded by earlier migrations carry proper names -- so a
Greek event read "Греция, ..., Other location" on the site while an Almaty one read "Другая локация".

The code fix (a gettext_noop marker plus the catalogue entries) stops new ones being made wrong.
This repairs the ones already there. Only nodes that really are a city's catch-all are touched, and
only in the locales that are empty or still hold the English source -- a name a person edited by
hand is left exactly as it is.
"""

from django.db import migrations

CANONICAL = {"name_ru": "Другая локация", "name_kk": "Басқа орын", "name_en": "Other location"}
# What a node is called when the translation never happened: the English source in every locale.
UNTRANSLATED = "Other location"


def repair(apps, schema_editor):
    Location = apps.get_model("locations", "Location")
    LocationFallback = apps.get_model("locations", "LocationFallback")

    fallback_ids = LocationFallback.objects.values_list("location_id", flat=True)
    repaired = 0
    for node in Location.objects.filter(pk__in=list(fallback_ids)):
        changed = []
        for field, canonical in CANONICAL.items():
            value = getattr(node, field) or ""
            if value and value != UNTRANSLATED:
                continue  # a real name, in this locale at least -- leave it alone
            if value != canonical:
                setattr(node, field, canonical)
                changed.append(field)
        # ``name`` is the untranslated column the tree sorts and searches on; it follows the Russian
        # name, which is how add_location_child writes it everywhere else.
        if (node.name or "") in ("", UNTRANSLATED) and node.name != CANONICAL["name_ru"]:
            node.name = CANONICAL["name_ru"]
            changed.append("name")
        if changed:
            node.save(update_fields=changed)
            repaired += 1
    if repaired:
        print(f"  repaired the name of {repaired} catch-all venue(s)")


def unrepair(apps, schema_editor):
    """Deliberately not reversible in data: nothing here is worth putting back wrong."""


class Migration(migrations.Migration):
    dependencies = [("locations", "0016_country_centroids")]

    operations = [migrations.RunPython(repair, unrepair)]
