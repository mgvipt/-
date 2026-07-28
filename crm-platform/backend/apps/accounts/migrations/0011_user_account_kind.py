from django.db import migrations, models


def mark_existing_accounts_as_staff(apps, schema_editor):
    """Preserve every pre-registration account as an internal staff account."""
    User = apps.get_model("accounts", "User")
    User.objects.all().update(account_kind="staff")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_user_about_user_birthday_user_interests_user_photo_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="account_kind",
            field=models.CharField(
                choices=[("client", "Клієнт"), ("staff", "Співробітник")],
                db_index=True,
                default="staff",
                max_length=12,
            ),
        ),
        migrations.RunPython(mark_existing_accounts_as_staff, migrations.RunPython.noop),
    ]
