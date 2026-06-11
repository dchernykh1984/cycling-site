from django.db.models.signals import post_delete, post_save

from .middleware import get_current_user

# Model import strings - resolved lazily to avoid circular imports at module load time.
# Each entry: (app_label, model_name)
_WATCHED_MODELS = [
    ("calendar_app", "Competition"),
    ("knowledge", "KnowledgeArticlePage"),
    ("knowledge", "LocationArticlePage"),
    ("news", "NewsPage"),
    ("registrations", "CompetitionRegistration"),
    ("knowledge", "DraftSubmission"),
]


def _make_save_handler(object_type):
    def handler(sender, instance, created, **kwargs):
        from .models import AuditLog

        update_fields = kwargs.get("update_fields")
        changes = ", ".join(sorted(update_fields)) if update_fields else ""
        AuditLog.objects.create(
            user=get_current_user(),
            action=AuditLog.ACTION_CREATED if created else AuditLog.ACTION_UPDATED,
            object_type=object_type,
            object_id=str(instance.pk),
            object_repr=str(instance)[:255],
            changes=changes,
        )

    handler.__name__ = f"audit_save_{object_type}"
    return handler


def _make_delete_handler(object_type):
    def handler(sender, instance, **kwargs):
        from .models import AuditLog

        AuditLog.objects.create(
            user=get_current_user(),
            action=AuditLog.ACTION_DELETED,
            object_type=object_type,
            object_id=str(instance.pk),
            object_repr=str(instance)[:255],
        )

    handler.__name__ = f"audit_delete_{object_type}"
    return handler


def connect_signals():
    """Connect post_save and post_delete signals for all watched models."""
    from django.apps import apps

    for app_label, model_name in _WATCHED_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        object_type = f"{app_label}.{model_name}"

        post_save.connect(
            _make_save_handler(object_type),
            sender=model,
            dispatch_uid=f"audit_save_{object_type}",
            weak=False,
        )
        post_delete.connect(
            _make_delete_handler(object_type),
            sender=model,
            dispatch_uid=f"audit_delete_{object_type}",
            weak=False,
        )
