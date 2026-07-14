# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("warehouse", "0013_stockdocument_supplier"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_drop",
            field=models.BooleanField(
                "Дроп (докупаємо під замовлення)",
                default=False,
                help_text="Товар, який ми продаємо ПІД замовлення і закуповуємо ПІСЛЯ продажу. Коли робиш прихід — закупівельна ціна автоматично оновлюється в УСІХ угодах з цим товаром (навіть у закритих) і в русі товару.",
            ),
        ),
    ]
