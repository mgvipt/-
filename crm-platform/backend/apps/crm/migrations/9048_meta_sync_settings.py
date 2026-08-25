from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "9047_kplink")]
    operations = [
        migrations.CreateModel(
            name="MetaSyncSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False)),
                ("ads_enabled", models.BooleanField(default=True)),
                ("content_enabled", models.BooleanField(default=True)),
                ("account_enabled", models.BooleanField(default=True)),
                ("ads_interval_min", models.PositiveIntegerField(default=360)),
                ("content_interval_min", models.PositiveIntegerField(default=360)),
                ("account_interval_min", models.PositiveIntegerField(default=360)),
                ("recent_days", models.PositiveIntegerField(default=7)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Настройки обновления маркетинга"},
        ),
    ]
