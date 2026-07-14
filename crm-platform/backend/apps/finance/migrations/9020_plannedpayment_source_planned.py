# -*- coding: utf-8 -*-
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "9019_findirection_internal_contact_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="plannedpayment",
            name="source_planned",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="derived_debts",
                to="finance.plannedpayment",
                help_text="Джерело-борг (напр. кредиторка магазину), що породив цей транзитний борг клієнта — видаляється каскадом",
            ),
        ),
    ]
