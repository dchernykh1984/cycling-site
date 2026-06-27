import contextlib
import os

from django.conf import settings
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(MigrateCommand):
    """Extends migrate with a one-time repair for the accounts.0001_initial
    inconsistency that occurs when the custom User model is deployed to a
    database that already has admin.0001_initial applied, and keeps the default
    Wagtail Site pointed at the canonical host on every deploy."""

    def handle(self, *app_labels, **options):
        _repair_accounts_initial_if_needed()
        super().handle(*app_labels, **options)
        _sync_default_site_host()


def _sync_default_site_host() -> None:
    """Point the default Wagtail Site -- and the django.contrib.sites Site that non-Wagtail
    sitemaps and allauth account emails build their URLs/branding from -- at the canonical host,
    so sitemaps, ``page.full_url`` and confirmation emails use the right domain. Driven by
    ``PRIMARY_HOST``, falling back to the first ``VIRTUAL_HOST``; a no-op when neither is set
    (local/test). This makes switching the live domain a config-only change: set
    ``PRIMARY_HOST=universalbicycle.team`` and redeploy."""
    host = os.environ.get("PRIMARY_HOST") or next(
        iter(os.environ.get("VIRTUAL_HOST", "").replace(",", " ").split()), ""
    )
    if not host:
        return
    # A cosmetic host sync must never break the deploy's migrate step (e.g. a table not ready), so
    # guard each independently. Reuse the Wagtail Site's display name as the brand for the
    # django.contrib.sites Site, which allauth confirmation emails render as ``site_name``.
    site_name = host
    with contextlib.suppress(Exception):
        from wagtail.models import Site

        default = Site.objects.filter(is_default_site=True).first()
        if default is not None:
            site_name = default.site_name or host
            Site.objects.filter(is_default_site=True).update(hostname=host, port=443)
    with contextlib.suppress(Exception):
        from django.contrib.sites.models import Site as DjangoSite

        DjangoSite.objects.filter(pk=settings.SITE_ID).update(domain=host, name=site_name)


def _repair_accounts_initial_if_needed() -> None:
    try:
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
    except Exception:
        return

    if ("admin", "0001_initial") not in applied:
        return
    if ("accounts", "0001_initial") in applied:
        return

    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)

    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)

    if "accounts_user" not in table_names:
        migration = executor.loader.get_migration("accounts", "0001_initial")
        state = executor.loader.project_state(("accounts", "0001_initial"), at_end=False)
        with connection.schema_editor() as schema_editor:
            migration.apply(state, schema_editor)

    recorder.record_applied("accounts", "0001_initial")
