from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0020_inventoryfactdraft")]
    operations = [
        migrations.AddField(model_name="product", name="pack_factor",
            field=models.DecimalField(decimal_places=4, default=1, max_digits=12,
                help_text="Скільки одиниць номенклатури (кг/л/шт) в 1 закупівельній одиниці (відро/мішок). 1 = однакові",
                verbose_name="Коеф. закупівлі→одиниця")),
    ]
