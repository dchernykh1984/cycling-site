from django.apps import AppConfig


class TrainerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trainer"
    verbose_name = "Virtual ride"

    def ready(self):
        # a member's Strava grant is revoked at Strava whatever deletes it, an account deletion too
        from . import strava  # noqa: F401
