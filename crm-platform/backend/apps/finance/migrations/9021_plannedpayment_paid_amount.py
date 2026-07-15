from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "9020_plannedpayment_source_planned")]
    operations = [
        migrations.AddField(
            model_name="plannedpayment",
            name="paid_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Погашено"),
        ),
    ]
