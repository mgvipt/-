import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("warehouse", "0016_product_shop_category_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="shop_specs",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="ShopCatalogImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_name", models.CharField(max_length=255)),
                ("source_hash", models.CharField(db_index=True, max_length=64)),
                ("status", models.CharField(choices=[("review", "На перевірці"), ("partially_applied", "Частково збережено"), ("applied", "Збережено")], db_index=True, default="review", max_length=24)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="ShopCatalogImportRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sheet_name", models.CharField(max_length=80)),
                ("source_row", models.PositiveIntegerField()),
                ("external_id", models.CharField(db_index=True, max_length=80)),
                ("source_data", models.JSONField(default=dict)),
                ("proposed_data", models.JSONField(default=dict)),
                ("warnings", models.JSONField(blank=True, default=list)),
                ("errors", models.JSONField(blank=True, default=list)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="warehouse.shopcatalogimportbatch")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shop_import_rows", to="warehouse.product")),
            ],
            options={"ordering": ["sheet_name", "source_row", "id"]},
        ),
        migrations.AddConstraint(
            model_name="shopcatalogimportrow",
            constraint=models.UniqueConstraint(fields=("batch", "sheet_name", "source_row"), name="uniq_shop_import_source_row"),
        ),
    ]
