from django.db import migrations, models


class Migration(migrations.Migration):
    """Погашення боргу З АВАНСУ клієнта: грошей у касу НЕ додаємо, але аванс маємо зменшити.
    Прапорець відрізняє такі погашення від «закрито вручну без руху грошей» (легасі Іваненка)."""

    dependencies = [("finance", "9025_plannedpayment_source_stock")]

    operations = [
        migrations.AddField(
            model_name="plannedpayment",
            name="paid_from_advance",
            field=models.BooleanField(default=False, verbose_name="Погашено з авансу клієнта"),
        ),
    ]
