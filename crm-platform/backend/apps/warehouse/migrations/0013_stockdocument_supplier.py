# -*- coding: utf-8 -*-
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("warehouse", "0012_product_min_price"),
        ("crm", "9024_changelogentry_section"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockdocument",
            name="supplier",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplied_documents", to="crm.contact",
                help_text="Постачальник (контрагент)",
            ),
        ),
        migrations.AddField(
            model_name="stockdocument",
            name="supplier_invoice",
            field=models.CharField("№ накладної постачальника", max_length=80, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="stockdocument",
            name="doc_date",
            field=models.DateField("Дата документа", null=True, blank=True),
        ),
    ]
