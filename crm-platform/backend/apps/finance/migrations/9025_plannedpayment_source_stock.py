from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "9024_findirection_parent"),
        ("warehouse", "0022_product_consumption"),
    ]

    operations = [
        migrations.AddField(
            model_name="plannedpayment",
            name="source_stock",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planned_payments", to="warehouse.stockdocument"),
        ),
    ]
