from django.db import migrations


class Migration(migrations.Migration):
    """
    The wagtailusers_userprofile FK was created pointing to auth_user (the
    default Django user table) before this project switched to a custom user
    model. All real users now live in accounts_user, so every attempt to create
    a UserProfile for a staff user causes a ForeignKeyViolation. This migration
    drops the wrong constraint and replaces it with one pointing to accounts_user.
    """

    dependencies = [
        ("accounts", "0009_owner_is_superuser"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE wagtailusers_userprofile
                DROP CONSTRAINT IF EXISTS wagtailusers_userprofile_user_id_59c92331_fk_auth_user_id;

                ALTER TABLE wagtailusers_userprofile
                ADD CONSTRAINT wagtailusers_userprofile_user_id_fk_accounts_user_id
                FOREIGN KEY (user_id) REFERENCES accounts_user(id)
                DEFERRABLE INITIALLY DEFERRED;
            """,
            reverse_sql="""
                ALTER TABLE wagtailusers_userprofile
                DROP CONSTRAINT IF EXISTS wagtailusers_userprofile_user_id_fk_accounts_user_id;

                ALTER TABLE wagtailusers_userprofile
                ADD CONSTRAINT wagtailusers_userprofile_user_id_59c92331_fk_auth_user_id
                FOREIGN KEY (user_id) REFERENCES auth_user(id)
                DEFERRABLE INITIALLY DEFERRED;
            """,
        )
    ]
