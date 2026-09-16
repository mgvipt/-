# 16.09.2026 (Олег): нові види фото відвантаження — накладна і архів тонування. Лише choices.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("warehouse", "0024_kit_tint_ops")]

    operations = [
        migrations.AlterField(
            model_name="warehousephoto",
            name="kind",
            field=models.CharField(max_length=16, choices=[
                ("buckets", "Відерця"), ("parcel", "Посилка"), ("cleanliness", "Чистота"), ("error_proof", "Доказ помилки"),
                ("invoice", "Накладна"), ("tint_archive", "Архів тонування")]),
        ),
    ]
