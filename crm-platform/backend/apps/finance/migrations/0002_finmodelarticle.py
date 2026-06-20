from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinModelArticle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(max_length=24, choices=[
                    ("revenue_fund", "Фонди виручки (% з виручки)"),
                    ("payment_fee", "Комісія еквайрингу (₴/угода)"),
                    ("variable", "Перемінні витрати (% від маржі)"),
                    ("fixed", "Постійні витрати (₴/міс)"),
                    ("upr_cat2", "УПР обов'язкові (₴/міс, у ТБ)"),
                    ("upr_cat3", "УПР відмовні (₴/міс)"),
                    ("warehouse_rate", "Ставки складу"),
                    ("config", "Конфіг / ліміти"),
                ])),
                ("name", models.CharField(max_length=160)),
                ("value", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("value_type", models.CharField(default="percent", max_length=24, choices=[
                    ("percent", "%"), ("fixed_sum_per_month", "₴/місяць"), ("fixed_per_deal", "₴/угода")])),
                ("unit", models.CharField(blank=True, default="", max_length=24)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["category", "sort_order", "id"]},
        ),
    ]
