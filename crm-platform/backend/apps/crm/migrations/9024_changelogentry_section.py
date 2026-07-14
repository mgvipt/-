# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9023_changelogentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="changelogentry",
            name="section",
            field=models.CharField(
                blank=True, default="", db_index=True, max_length=48,
                help_text="Блок-розділ для групування: Фінанси / Склад / Клієнти / Загальне",
            ),
        ),
    ]
