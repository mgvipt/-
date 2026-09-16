# 16.09.2026 (Олег): план онлайн і офлайн окремо. Лише нові поля з нулем за замовчуванням.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("finance", "9028_transaction_date_localdate")]

    operations = [
        migrations.AddField(model_name="managerplan", name=n, field=models.DecimalField(decimal_places=2, default=0, max_digits=14))
        for n in ("online_min", "online_target", "online_ambition", "offline_min", "offline_target", "offline_ambition")
    ]
