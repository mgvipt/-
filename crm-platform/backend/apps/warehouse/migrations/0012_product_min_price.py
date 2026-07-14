# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("warehouse", "0011_product_cost_pct"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="min_price",
            field=models.DecimalField(
                "Минимальная цена за позицию", max_digits=12, decimal_places=2, default=0,
                help_text="Минимум за строку в сделке: если цена×кол-во меньше — берётся этот минимум. 0 = без минимума. Пример: сверление 17/см, но минимум 1500.",
            ),
        ),
    ]
