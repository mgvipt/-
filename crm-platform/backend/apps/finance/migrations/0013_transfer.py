import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0012_attachment")]
    operations = [
        migrations.AlterField(
            model_name="transaction", name="direction",
            field=models.CharField(choices=[("in", "Доход"), ("out", "Расход"), ("transfer", "Переказ")], max_length=10)),
        migrations.AddField(
            model_name="transaction", name="transfer_account",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="incoming_transfers", to="finance.account",
                help_text="Рахунок-отримувач (для переказу)")),
    ]
