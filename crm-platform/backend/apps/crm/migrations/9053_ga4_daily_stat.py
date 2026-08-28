from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9052_contact_expense_adjust"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ga4DailyStat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("property_id", models.CharField(db_index=True, max_length=32)),
                ("site", models.CharField(blank=True, default="", max_length=120)),
                ("date", models.DateField(db_index=True)),
                ("sessions", models.PositiveIntegerField(default=0)),
                ("active_users", models.PositiveIntegerField(default=0)),
                ("new_users", models.PositiveIntegerField(default=0)),
                ("key_events", models.PositiveIntegerField(default=0)),
                ("sources", models.JSONField(blank=True, default=dict)),
                ("synced_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="ga4dailystat",
            constraint=models.UniqueConstraint(fields=("property_id", "date"), name="uniq_ga4_property_day"),
        ),
        migrations.AddIndex(
            model_name="ga4dailystat",
            index=models.Index(fields=["site", "date"], name="crm_ga4_site_day"),
        ),
    ]
