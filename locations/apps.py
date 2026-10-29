from django.apps import AppConfig


class LocationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "locations"

    def ready(self):
        from locations import checks  # noqa: F401 -- registers the startup checks
