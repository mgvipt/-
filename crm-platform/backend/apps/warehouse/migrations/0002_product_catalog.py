from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("warehouse", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("bitrix_id", models.IntegerField(blank=True, db_index=True, null=True, unique=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="warehouse.productcategory")),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "Product categories"},
        ),
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="warehouse.productcategory"),
        ),
        migrations.AddField(
            model_name="product",
            name="currency",
            field=models.CharField(default="UAH", max_length=8),
        ),
        migrations.AddField(
            model_name="product",
            name="bitrix_id",
            field=models.IntegerField(blank=True, db_index=True, null=True, unique=True, verbose_name="ID в Bitrix"),
        ),
    ]
