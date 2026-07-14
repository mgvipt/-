# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9024_changelogentry_section"),
    ]

    operations = [
        migrations.AddField(
            model_name="dealitem",
            name="discount_amount",
            field=models.DecimalField(
                max_digits=12, decimal_places=2, default=0,
                help_text="Знижка на позицію фіксованою сумою ₴ (якщо >0 — має пріоритет над %)",
            ),
        ),
    ]
