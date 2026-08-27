from django.apps import AppConfig


class HomeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "home"

    def ready(self):
        # IndexNow spans several apps (events, news, knowledge), so it is wired once from here
        # rather than three times from each of them.
        from cycling_site.indexnow import connect_signals

        connect_signals()
