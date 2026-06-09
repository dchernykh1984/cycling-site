import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from django.db.models.signals import post_migrate

        import accounts.signals  # noqa: F401

        post_migrate.connect(
            _setup_group_permissions,
            dispatch_uid="accounts.setup_group_permissions",
        )


def _setup_group_permissions(sender, **kwargs):
    """Assign Wagtail admin access and User CRUD permissions to admins/owners groups."""
    from django.apps import apps
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    try:
        access_admin = Permission.objects.filter(
            codename="access_admin",
            content_type__app_label="wagtailadmin",
        ).first()
        if access_admin is None:
            return  # wagtailadmin migrations not yet applied

        user_model = apps.get_model("accounts", "User")
        user_ct = ContentType.objects.get_for_model(user_model)
        user_perms = {p.codename: p for p in Permission.objects.filter(content_type=user_ct)}

        admins, _ = Group.objects.get_or_create(name="Admins")
        admins.permissions.add(
            access_admin,
            *[user_perms[c] for c in ("view_user", "change_user", "add_user") if c in user_perms],
        )

        owners, _ = Group.objects.get_or_create(name="Owners")
        owners.permissions.add(
            access_admin,
            *[user_perms[c] for c in ("view_user", "change_user", "add_user", "delete_user") if c in user_perms],
        )
    except Exception:
        logger.warning("Could not set up default group permissions", exc_info=True)
