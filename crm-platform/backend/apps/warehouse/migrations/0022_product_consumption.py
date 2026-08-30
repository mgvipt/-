from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0021_product_pack_factor")]
    operations = [
        migrations.AddField(
            model_name="product", name="consumption_per_m2",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True,
                help_text="Скільки одиниць товару треба на 1 м² для ФІНІШНОГО результату (з усіма шарами). Якщо заповнено — у сделці кількість рахується автоматично: площа × витрата.",
                verbose_name="Витрата на 1 м²"),
        ),
    ]
