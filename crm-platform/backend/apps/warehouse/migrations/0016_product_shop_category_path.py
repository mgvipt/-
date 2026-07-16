from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0015_shop_catalog_admin")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="shop_category_path",
            field=models.JSONField(blank=True, default=list, verbose_name="Категорія на сайті"),
        ),
    ]
