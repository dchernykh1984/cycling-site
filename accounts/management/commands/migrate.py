from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(MigrateCommand):
    """Extends migrate with a one-time repair for the accounts.0001_initial
    inconsistency that occurs when the custom User model is deployed to a
    database that already has admin.0001_initial applied."""

    def handle(self, *app_labels, **options):
        _repair_accounts_initial_if_needed()
        super().handle(*app_labels, **options)


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
