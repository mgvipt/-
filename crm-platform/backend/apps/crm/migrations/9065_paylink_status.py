from django.db import migrations, models


class Migration(migrations.Migration):
    """18.09.2026: статус і причина відмови LiqPay на посиланні оплати (для картки сделки і сповіщення)."""

    dependencies = [("crm", "9064_dealitem_tint_mode_sample")]

    operations = [
        migrations.AddField(model_name="paylink", name="status",
                            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Статус LiqPay")),
        migrations.AddField(model_name="paylink", name="error",
                            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Причина відмови")),
        migrations.AddField(model_name="paylink", name="status_at",
                            field=models.DateTimeField(blank=True, null=True)),
    ]
