# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9025_dealitem_discount_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="edrpou",
            field=models.CharField("ЄДРПОУ / ІПН", max_length=32, blank=True, default="", db_index=True),
        ),
        migrations.AddField(
            model_name="contact",
            name="iban",
            field=models.CharField("IBAN / рахунок", max_length=64, blank=True, default=""),
        ),
    ]
