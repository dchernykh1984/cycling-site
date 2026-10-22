from django.apps import AppConfig


class GalleryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gallery"
    verbose_name = "Gallery"

    def ready(self):
        from gallery import signals  # noqa: F401  (registers the file clean-up)
