from django.db import migrations, models


class Migration(migrations.Migration):
    """19.09.2026: нові типи помилок складу (дощечка, наклейка, скотч, недостача) — лише choices, без зміни даних."""

    dependencies = [("warehouse", "0026_washed_samples")]

    operations = [
        migrations.AlterField(
            model_name="warehouseerror", name="kind",
            field=models.CharField(choices=[
                ("wrong_material", "Невірний матеріал"), ("wrong_tint", "Невірна тонировка"),
                ("wrong_qty", "Невірна кількість"), ("damaged", "Пошкоджено"), ("lost_np", "Втрачено в НП"),
                ("no_board", "Не поклали дощечку в тест-набір"), ("sticker_bad", "Наклейка нечитабельна або з помилкою"),
                ("sticker_miss", "Не наклеєна наклейка"), ("lid_tape", "Кришка відра не проклеєна скотчем по колу"),
                ("inv_short", "Недостача після інвентаризації"), ("other", "Інше")],
                default="other", max_length=16),
        ),
    ]
