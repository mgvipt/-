import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Відомість місяця (затвердити / перевідкрити) і привʼязка фактичних виплат з журналу. Лише нові таблиці payroll_*."""

    dependencies = [
        ("payroll", "0001_initial"),
        ("finance", "9028_transaction_date_localdate"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PayrollRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.CharField(db_index=True, max_length=7)),
                ("version", models.PositiveSmallIntegerField(default=1)),
                ("status", models.CharField(choices=[("approved", "Затверджено"), ("reopened", "Перевідкрито")], default="approved", max_length=10)),
                ("lines", models.JSONField(blank=True, default=list)),
                ("inputs", models.JSONField(blank=True, default=dict)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("company_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("approved_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reopened_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("reopened_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("scheme", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="runs", to="payroll.payscheme")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payroll_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-period", "user_id", "-version"], "unique_together": {("period", "user", "version")}},
        ),
        migrations.CreateModel(
            name="PayrollPayout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("linked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payouts", to="payroll.payrollrun")),
                ("transaction", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payroll_payouts", to="finance.transaction")),
            ],
            options={"unique_together": {("run", "transaction")}},
        ),
    ]
