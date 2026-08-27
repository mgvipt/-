from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9049_meta_paid_follow_stats"),
    ]

    operations = [
        migrations.AddField(
            model_name="metaaddailystat",
            name="result_indicator",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="metaaddailystat",
            name="result_value",
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
