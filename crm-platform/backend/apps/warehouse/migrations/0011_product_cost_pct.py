# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("warehouse", "0010_product_track_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="cost_pct",
            field=models.DecimalField(
                "Себестоимость, % от цены", max_digits=5, decimal_places=2, default=0,
                help_text="Для услуг/работ, где мастеру платим долю: себестоимость = цена × этот %. 0 = использовать фиксированную Себестоимость. Пример: монтаж, мастер получает 80% → впиши 80.",
            ),
        ),
    ]
