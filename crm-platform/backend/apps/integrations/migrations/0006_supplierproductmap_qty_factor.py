from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integrations", "0005_supplierproductmap")]
    operations = [
        migrations.AddField(
            model_name="supplierproductmap",
            name="qty_factor",
            field=models.DecimalField(decimal_places=4, default=1, max_digits=12,
                help_text="Скільки НАШИХ одиниць (напр. кг) в 1 одиниці постачальника (напр. відро). 1 = однакові одиниці",
                verbose_name="Коеф. одиниць складу за 1 одиницю постачальника"),
        ),
    ]
