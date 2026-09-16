# 16.09.2026 (Олег): нові типи нарахувань складу — тонування набору (каталог / індивідуальне). Лише choices.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("warehouse", "0023_alter_warehousepayrollentry_op_type")]

    operations = [
        migrations.AlterField(
            model_name="warehousepayrollentry",
            name="op_type",
            field=models.CharField(max_length=20, choices=[
                ("shipment_weight", "Вага відвантаження"), ("packing", "Упаковка"), ("tinting", "Тонування"),
                ("workday", "Робочий день"), ("error", "Помилка"), ("wrong_material", "Невірний матеріал"),
                ("bonus_initiative", "Бонус-ідея"), ("bonus_cleanliness", "Бонус-чистота"),
                ("test_set", "Збірка тестового набору"), ("kit_tint_cat", "Тонування набору: каталог"),
                ("kit_tint_ind", "Тонування набору: індивідуальне")]),
        ),
    ]
