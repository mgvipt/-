import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0009_fundallocation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="finmodelarticle",
            name="code",
            field=models.CharField(blank=True, default="", max_length=40,
                help_text="Машинний код для службових параметрів (salary_base тощо)"),
        ),
        migrations.CreateModel(
            name="ManagerPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.CharField(help_text="YYYY-MM", max_length=7)),
                ("min_revenue", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("target_revenue", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("ambition_revenue", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kpi_plans", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-period"], "unique_together": {("user", "period")}},
        ),
    ]
