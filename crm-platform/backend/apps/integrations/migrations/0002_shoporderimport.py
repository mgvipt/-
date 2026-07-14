from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "9025_dealitem_discount_amount"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopOrderImport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_uuid", models.UUIDField(unique=True)),
                ("order_number", models.CharField(max_length=64, unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("deal", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shop_order_import", to="crm.deal")),
            ],
            options={"ordering": ["-imported_at"]},
        ),
    ]
