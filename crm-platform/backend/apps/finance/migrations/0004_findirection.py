from django.db import migrations, models
import django.db.models.deletion


def seed(apps, schema_editor):
    D = apps.get_model("finance", "FinDirection")
    # Напрямки з Finmap (Проекти) + планові доходи/витрати = реальні річні з Finmap (орієнтир)
    rows = [
        ("ДЕКОР Товари (Офлайн/Онлайн)", 2868092.72, 2492475.52, 10),
        ("Об'єкти (Матеріали+Робота)", 1307311.00, 858840.03, 20),
        ("Hardwork / Демонтаж (алмазна різка, свердління)", 176988.94, 138696.96, 30),
        ("Маркетинг", 17500.00, 530.96, 40),
        ("Особисті витрати", 199000.00, 467939.73, 50),
        ("Без напрямку", 0, 0, 90),
    ]
    for name, inc, exp, order in rows:
        D.objects.get_or_create(name=name, defaults={"plan_income": inc, "plan_expense": exp, "sort_order": order})


class Migration(migrations.Migration):
    dependencies = [("finance", "0003_seed_finmodel")]
    operations = [
        migrations.CreateModel(
            name="FinDirection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=160)),
                ("plan_income", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("plan_expense", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddField(
            model_name="transaction",
            name="fin_direction",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="finance.findirection"),
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
