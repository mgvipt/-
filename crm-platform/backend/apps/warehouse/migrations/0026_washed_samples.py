# 16.09.2026 (Олег): мите відро (пара тари), рецепти викрасок з А3, вибір митої тари у відвантаженні, нові типи нарахувань.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("warehouse", "0025_photo_invoice_tint_archive")]

    operations = [
        migrations.AddField(model_name="warehousejob", name="washed_tare", field=models.JSONField(blank=True, default=dict)),
        migrations.CreateModel(
            name="WashedTare",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("active", models.BooleanField(default=True)),
                ("new", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="washed_pair", to="warehouse.product")),
                ("washed", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="washed_of", to="warehouse.product")),
            ],
        ),
        migrations.CreateModel(
            name="SampleRecipe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("per_sheet", models.PositiveSmallIntegerField(default=4)),
                ("lines", models.JSONField(blank=True, default=list, help_text='[{"product": id, "kg": 0.05}] на 1 аркуш А3')),
                ("active", models.BooleanField(default=True)),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sample_recipes", to="warehouse.product")),
                ("paper", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="warehouse.product")),
            ],
        ),
        migrations.AlterField(
            model_name="warehousepayrollentry",
            name="op_type",
            field=models.CharField(max_length=20, choices=[
                ("shipment_weight", "Вага відвантаження"), ("packing", "Упаковка"), ("tinting", "Тонування"),
                ("workday", "Робочий день"), ("error", "Помилка"), ("wrong_material", "Невірний матеріал"),
                ("bonus_initiative", "Бонус-ідея"), ("bonus_cleanliness", "Бонус-чистота"),
                ("test_set", "Збірка тестового набору"), ("kit_tint_cat", "Тонування набору: каталог"),
                ("kit_tint_ind", "Тонування набору: індивідуальне"), ("washed_bucket", "Мите відро"), ("samples", "Викраски")]),
        ),
    ]
