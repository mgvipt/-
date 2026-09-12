import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Дата операції за замовчуванням — київська (не UTC контейнера): нічна оплата не падає у вчорашній закритий день."""

    dependencies = [("finance", "9027_daysnapshot")]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="date",
            field=models.DateField(db_index=True, default=django.utils.timezone.localdate),
        ),
    ]
