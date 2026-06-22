from django.db import migrations, models
import django.db.models.functions


def fill_uah(apps, schema_editor):
    Transaction = apps.get_model("finance", "Transaction")
    Transaction.objects.update(amount_uah=models.F("amount"))


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0010_salary_plans"),
    ]

    operations = [
        migrations.AddField(model_name="transaction", name="counterparty",
            field=models.CharField(blank=True, default="", help_text="Контрагент (від кого/кому)", max_length=160)),
        migrations.AddField(model_name="transaction", name="currency",
            field=models.CharField(default="UAH", help_text="Валюта операції", max_length=3)),
        migrations.AddField(model_name="transaction", name="rate",
            field=models.DecimalField(decimal_places=4, default=1, help_text="Курс до гривні (1 одиниця валюти = N грн)", max_digits=12)),
        migrations.AddField(model_name="transaction", name="amount_uah",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Сума у гривні (amount × rate) — для аналітики", max_digits=14)),
        migrations.RunPython(fill_uah, migrations.RunPython.noop),
        migrations.CreateModel(
            name="AdvisoryReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(default="profit_x2", max_length=32)),
                ("title", models.CharField(default="План зростання прибутку", max_length=200)),
                ("body", models.TextField(help_text="Markdown")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
