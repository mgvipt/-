from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    # Client ownership is explicit; this migration never matches contacts by phone.
    dependencies = [
        ("accounts", "0011_user_account_kind"),
        ("crm", "9031_zamer_estimate_calcsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="portal_user",
            field=models.OneToOneField(
                blank=True,
                help_text="Личный клиентский аккаунт приложения; не назначается по совпадению телефона",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="portal_contact",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
