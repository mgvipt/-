from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9053_ga4_daily_stat"),
    ]

    operations = [
        migrations.AddField(model_name="ga4dailystat", name="channels",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="ga4dailystat", name="engagement_rate",
                            field=models.FloatField(default=0)),
        migrations.AddField(model_name="ga4dailystat", name="avg_duration_sec",
                            field=models.PositiveIntegerField(default=0)),
    ]
