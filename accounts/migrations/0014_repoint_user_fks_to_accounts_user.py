from django.db import migrations

from accounts.user_fk_repair import REPOINT_USER_FKS_SQL


class Migration(migrations.Migration):
    """Repoint legacy user FKs from auth_user to accounts_user on the production DB (#124).

    Database-only: the migration *state* already references accounts.User (the models say
    so), only the physical constraints on production drifted. So this carries no state
    operations and is a no-op everywhere the schema is already correct.
    """

    dependencies = [
        ("accounts", "0013_rename_last_mail_action_at"),
    ]

    operations = [
        migrations.RunSQL(REPOINT_USER_FKS_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
