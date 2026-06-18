from django.db import migrations

from accounts.user_fk_repair import DROP_LEGACY_AUTH_USER_SQL


class Migration(migrations.Migration):
    """Drop the now-unused legacy auth_user table and its m2m tables (#124 cleanup).

    Runs after 0014 has repointed every real user FK to accounts_user, so auth_user is
    no longer referenced. Database-only and a no-op where auth_user never existed.
    """

    dependencies = [
        ("accounts", "0014_repoint_user_fks_to_accounts_user"),
    ]

    operations = [
        migrations.RunSQL(DROP_LEGACY_AUTH_USER_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
