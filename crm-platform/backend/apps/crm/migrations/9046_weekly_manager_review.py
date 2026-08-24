from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "9045_meta_account_daily_stat"),
    ]

    operations = [
        migrations.CreateModel(
            name="WeeklyManagerReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("period", models.CharField(blank=True, default="", max_length=40)),
                ("summary", models.TextField(blank=True, default="")),
                ("data", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ["-id"]},
        ),
    ]
