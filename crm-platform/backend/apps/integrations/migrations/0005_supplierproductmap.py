from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0004_incomingdoc"),
        ("warehouse", "0015_shop_catalog_admin"),
    ]
    operations = [
        migrations.CreateModel(
            name="SupplierProductMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("supplier_key", models.CharField(db_index=True, default="", max_length=120)),
                ("their_name", models.CharField(max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="warehouse.product")),
            ],
            options={"unique_together": {("supplier_key", "their_name")}},
        ),
    ]
