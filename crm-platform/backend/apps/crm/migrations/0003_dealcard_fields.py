from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_dealitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="loyalty_tag",
            field=models.CharField(blank=True, default="", help_text="Новый/Активный/VIP/Спящий", max_length=24),
        ),
        migrations.AddField(
            model_name="contact",
            name="birthday",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deal",
            name="discount_pct",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="deal",
            name="pay_type",
            field=models.CharField(blank=True, default="", help_text="Полная/Предоплата 50%/Послеоплата НП", max_length=40),
        ),
        migrations.AddField(
            model_name="deal",
            name="ttn",
            field=models.CharField(blank=True, default="", max_length=40, verbose_name="ТТН Нова Пошта"),
        ),
        migrations.AddField(
            model_name="deal",
            name="checkbox_status",
            field=models.CharField(blank=True, default="none", help_text="none/аванс/финальный", max_length=16),
        ),
    ]
