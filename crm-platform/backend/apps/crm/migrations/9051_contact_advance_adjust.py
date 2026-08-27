from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("crm", "9050_meta_ad_results")]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="advance_adjust",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14,
                                      help_text="Ручна поправка до розрахованого авансу. Рухів грошей НЕ створює.",
                                      verbose_name="Коригування авансу"),
        ),
        migrations.AddField(
            model_name="contact",
            name="advance_adjust_note",
            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Причина коригування"),
        ),
    ]
