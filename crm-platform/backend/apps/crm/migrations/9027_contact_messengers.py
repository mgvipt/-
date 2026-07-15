# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9026_contact_edrpou"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="messengers",
            field=models.JSONField(
                default=list,
                blank=True,
                help_text="Кілька месенджерів/контактів клієнта (IG/TG/Viber/номер) — список посилань",
            ),
        ),
    ]
