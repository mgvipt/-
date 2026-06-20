from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_dealcard_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="owner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contacts_owned", to=settings.AUTH_USER_MODEL, help_text="Ответственный менеджер клиента"),
        ),
        migrations.AddField(
            model_name="contact",
            name="last_touch_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
