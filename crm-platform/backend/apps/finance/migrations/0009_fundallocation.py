import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_fund_hierarchy"),
    ]

    operations = [
        migrations.CreateModel(
            name="FundAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("period", models.CharField(help_text="YYYY-MM", max_length=7)),
                ("comment", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fund_allocations", to="finance.account")),
                ("fin_direction", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fund_allocations", to="finance.findirection")),
                ("fund", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="finance.finmodelarticle")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
