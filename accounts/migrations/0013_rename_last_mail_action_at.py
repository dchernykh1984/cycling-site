from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_email_confirmation_sent_at"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="email_confirmation_sent_at",
            new_name="last_mail_action_at",
        ),
    ]
