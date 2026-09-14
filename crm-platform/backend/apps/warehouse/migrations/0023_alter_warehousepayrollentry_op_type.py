# 14.09.2026 (wh-accrual): новий тип рядка ЗП складу «Збірка тестового набору» (test_set).
# ЛИШЕ choices — у PostgreSQL для CharField це не змінює таблицю (ні ALTER, ні блокувань).
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0022_product_consumption")]
    operations = [
        migrations.AlterField(
            model_name="warehousepayrollentry",
            name="op_type",
            field=models.CharField(
                choices=[
                    ("shipment_weight", "Вага відвантаження"), ("packing", "Упаковка"), ("tinting", "Тонування"),
                    ("workday", "Робочий день"), ("error", "Помилка"), ("wrong_material", "Невірний матеріал"),
                    ("bonus_initiative", "Бонус-ідея"), ("bonus_cleanliness", "Бонус-чистота"),
                    ("test_set", "Збірка тестового набору"),
                ],
                max_length=20,
            ),
        ),
    ]
